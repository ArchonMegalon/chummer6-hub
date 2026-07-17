#!/usr/bin/env bash
set -euo pipefail

QBIT_REPO_ROOT="${QBIT_REPO_ROOT:-/docker/chummercomplete/chummer.run-services}"
QBIT_PYTHON_BIN="${QBIT_PYTHON_BIN:-/usr/bin/python3}"
QBIT_HYGIENE_SCRIPT="${QBIT_HYGIENE_SCRIPT:-$QBIT_REPO_ROOT/scripts/materialize_qbittorrent_staging_hygiene.py}"
QBIT_HYGIENE_OUTPUT="${QBIT_HYGIENE_OUTPUT:-/run/QBITTORRENT_STAGING_HYGIENE.generated.json}"
QBIT_HYGIENE_TIMEOUT_SECONDS="${QBIT_HYGIENE_TIMEOUT_SECONDS:-30}"
QBIT_MIN_DEAD_STALLED_AGE_MINUTES="${QBIT_MIN_DEAD_STALLED_AGE_MINUTES:-5}"
QBIT_MIN_DEAD_META_AGE_MINUTES="${QBIT_MIN_DEAD_META_AGE_MINUTES:-45}"
QBIT_MIN_DEAD_CHECKING_AGE_MINUTES="${QBIT_MIN_DEAD_CHECKING_AGE_MINUTES:-90}"
QBIT_MAX_RECOVERY_CYCLES="${QBIT_MAX_RECOVERY_CYCLES:-2}"
QBIT_RECOVERY_WAIT_SECONDS="${QBIT_RECOVERY_WAIT_SECONDS:-5}"
QBIT_DELETE_DEAD_STALLED="${QBIT_DELETE_DEAD_STALLED:-0}"
QBIT_DELETE_DEAD_META="${QBIT_DELETE_DEAD_META:-0}"
QBIT_DELETE_DEAD_CHECKING="${QBIT_DELETE_DEAD_CHECKING:-0}"
QBIT_ENSURE_QUEUEING="${QBIT_ENSURE_QUEUEING:-0}"
QBIT_CLEAR_FORCED_DOWNLOADS="${QBIT_CLEAR_FORCED_DOWNLOADS:-1}"
LOCKFILE="${QBIT_HYGIENE_LOCKFILE:-/run/qbittorrent-staging-hygiene-watchdog.lock}"

exec 9>"$LOCKFILE"
flock -n 9 || exit 0

log() {
  logger -t qbittorrent-staging-hygiene-watchdog -- "$*"
  echo "[qbittorrent-staging-hygiene-watchdog] $*"
}

if [[ ! -f "$QBIT_HYGIENE_SCRIPT" ]]; then
  log "missing qBittorrent hygiene script: $QBIT_HYGIENE_SCRIPT"
  exit 1
fi

if ! command -v "$QBIT_PYTHON_BIN" >/dev/null 2>&1; then
  log "missing python interpreter: $QBIT_PYTHON_BIN"
  exit 1
fi

mkdir -p "$(dirname "$QBIT_HYGIENE_OUTPUT")"

args=(
  --output "$QBIT_HYGIENE_OUTPUT"
  --timeout-seconds "$QBIT_HYGIENE_TIMEOUT_SECONDS"
  --min-dead-stalled-age-minutes "$QBIT_MIN_DEAD_STALLED_AGE_MINUTES"
  --min-dead-meta-age-minutes "$QBIT_MIN_DEAD_META_AGE_MINUTES"
  --min-dead-checking-age-minutes "$QBIT_MIN_DEAD_CHECKING_AGE_MINUTES"
  --max-recovery-cycles "$QBIT_MAX_RECOVERY_CYCLES"
  --recovery-wait-seconds "$QBIT_RECOVERY_WAIT_SECONDS"
  --apply-requeue-dead-stalled-downloads
  --apply-requeue-dead-meta-downloads
  --apply-requeue-dead-checking-downloads
)

if [[ "$QBIT_ENSURE_QUEUEING" == "1" ]]; then
  args+=(--apply-enable-queueing)
fi
if [[ "$QBIT_CLEAR_FORCED_DOWNLOADS" == "1" ]]; then
  args+=(--apply-clear-forced-downloads)
fi
if [[ "$QBIT_DELETE_DEAD_STALLED" == "1" ]]; then
  args+=(--apply-delete-dead-stalled-downloads)
fi
if [[ "$QBIT_DELETE_DEAD_META" == "1" ]]; then
  args+=(--apply-delete-dead-meta-downloads)
fi
if [[ "$QBIT_DELETE_DEAD_CHECKING" == "1" ]]; then
  args+=(--apply-delete-dead-checking-downloads)
fi

log "starting qBittorrent staging-hygiene recovery lane"
"$QBIT_PYTHON_BIN" "$QBIT_HYGIENE_SCRIPT" "${args[@]}"
status=$?
log "qBittorrent staging-hygiene recovery lane completed (python exit=$status)"
exit "$status"
