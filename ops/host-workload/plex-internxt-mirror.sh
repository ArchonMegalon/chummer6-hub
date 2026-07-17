#!/usr/bin/env bash
set -euo pipefail

PCLOUD_ROOT="${PCLOUD_ROOT:-/mnt/pcloud/PLEX}"
INTERNXT_ROOT="${INTERNXT_ROOT:-/mnt/internxt/PLEX}"
MOVIES_SOURCE="${MOVIES_SOURCE:-$PCLOUD_ROOT/Movies}"
MOVIES_DEST="${MOVIES_DEST:-$INTERNXT_ROOT/Movies}"
TV_SOURCE="${TV_SOURCE:-$PCLOUD_ROOT/TV}"
TV_DEST="${TV_DEST:-$INTERNXT_ROOT/TV}"
REQUESTED_ROOT="${REQUESTED_ROOT:-$PCLOUD_ROOT/Requested}"
REQUESTED_MOVIES_SOURCE="${REQUESTED_MOVIES_SOURCE:-$REQUESTED_ROOT/Movies}"
REQUESTED_TV_SOURCE="${REQUESTED_TV_SOURCE:-$REQUESTED_ROOT/TV}"
REQUESTED_UNSORTED_SOURCE="${REQUESTED_UNSORTED_SOURCE:-$REQUESTED_ROOT/Unsorted}"
REQUESTED_INBOX_SOURCE="${REQUESTED_INBOX_SOURCE:-$REQUESTED_ROOT/_inbox}"
RSYNC_BIN="${RSYNC_BIN:-/usr/bin/rsync}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
PROBE_TIMEOUT_SECS="${PROBE_TIMEOUT_SECS:-30}"

STATE_DIR="${STATE_DIR:-/run/plex-internxt-mirror}"
LOCKFILE="$STATE_DIR/plex-internxt-mirror.lock"
STATUS_FILE="$STATE_DIR/status.json"

mkdir -p "$STATE_DIR"

exec 9>"$LOCKFILE"
flock -n 9 || exit 0

RUN_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
FINALIZED=0
OVERALL_TOTAL=0
CURRENT_STATUS="starting"
CURRENT_PHASE="init"
CURRENT_PHASE_LABEL="Initializing"
CURRENT_PHASE_CURRENT=0
CURRENT_PHASE_TOTAL=0
CURRENT_OVERALL_CURRENT=0
CURRENT_NAME=""
CURRENT_DETAIL=""
CURRENT_NOTE="starting"
CURRENT_LAST_ERROR=""
CURRENT_EXIT_CODE=0

log() {
  logger -t plex-internxt-mirror -- "$*"
  echo "[plex-internxt-mirror] $*"
}

fail() {
  CURRENT_STATUS="failed"
  CURRENT_NOTE="failed"
  CURRENT_LAST_ERROR="$*"
  log "$*"
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

probe_dir() {
  local path="$1"
  timeout "$PROBE_TIMEOUT_SECS" ls -1A "$path" >/dev/null 2>&1
}

write_status() {
  local status="$1" phase="$2" phase_label="$3" phase_current="$4" phase_total="$5" overall_current="$6" overall_total="$7"
  local current_name="${8:-}" current_detail="${9:-}" note="${10:-}" last_error="${11:-}" exit_code="${12:-0}"

  STATUS_STATUS="$status" \
  STATUS_PHASE="$phase" \
  STATUS_PHASE_LABEL="$phase_label" \
  STATUS_PHASE_CURRENT="$phase_current" \
  STATUS_PHASE_TOTAL="$phase_total" \
  STATUS_OVERALL_CURRENT="$overall_current" \
  STATUS_OVERALL_TOTAL="$overall_total" \
  STATUS_CURRENT_NAME="$current_name" \
  STATUS_CURRENT_DETAIL="$current_detail" \
  STATUS_NOTE="$note" \
  STATUS_LAST_ERROR="$last_error" \
  STATUS_EXIT_CODE="$exit_code" \
  STATUS_RUN_STARTED_AT="$RUN_STARTED_AT" \
  STATUS_UPDATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "$PYTHON_BIN" - "$STATUS_FILE" <<'PY'
import json
import os
import sys
from pathlib import Path


def int_env(name: str) -> int:
    raw = str(os.environ.get(name, "0")).strip()
    try:
        return int(raw)
    except ValueError:
        return 0


path = Path(sys.argv[1])
tmp = path.with_name(f"{path.name}.tmp")
payload = {
    "status": str(os.environ.get("STATUS_STATUS", "")).strip(),
    "phase": str(os.environ.get("STATUS_PHASE", "")).strip(),
    "phase_label": str(os.environ.get("STATUS_PHASE_LABEL", "")).strip(),
    "phase_current": int_env("STATUS_PHASE_CURRENT"),
    "phase_total": int_env("STATUS_PHASE_TOTAL"),
    "overall_current": int_env("STATUS_OVERALL_CURRENT"),
    "overall_total": int_env("STATUS_OVERALL_TOTAL"),
    "current_name": str(os.environ.get("STATUS_CURRENT_NAME", "")).strip(),
    "current_detail": str(os.environ.get("STATUS_CURRENT_DETAIL", "")).strip(),
    "note": str(os.environ.get("STATUS_NOTE", "")).strip(),
    "last_error": str(os.environ.get("STATUS_LAST_ERROR", "")).strip(),
    "exit_code": int_env("STATUS_EXIT_CODE"),
    "run_started_at": str(os.environ.get("STATUS_RUN_STARTED_AT", "")).strip(),
    "updated_at": str(os.environ.get("STATUS_UPDATED_AT", "")).strip(),
}
tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
tmp.replace(path)
PY
}

update_status() {
  CURRENT_STATUS="$1"
  CURRENT_PHASE="$2"
  CURRENT_PHASE_LABEL="$3"
  CURRENT_PHASE_CURRENT="$4"
  CURRENT_PHASE_TOTAL="$5"
  CURRENT_OVERALL_CURRENT="$6"
  OVERALL_TOTAL="$7"
  CURRENT_NAME="${8:-}"
  CURRENT_DETAIL="${9:-}"
  CURRENT_NOTE="${10:-}"
  CURRENT_LAST_ERROR="${11:-$CURRENT_LAST_ERROR}"
  CURRENT_EXIT_CODE="${12:-0}"
  write_status \
    "$CURRENT_STATUS" \
    "$CURRENT_PHASE" \
    "$CURRENT_PHASE_LABEL" \
    "$CURRENT_PHASE_CURRENT" \
    "$CURRENT_PHASE_TOTAL" \
    "$CURRENT_OVERALL_CURRENT" \
    "$OVERALL_TOTAL" \
    "$CURRENT_NAME" \
    "$CURRENT_DETAIL" \
    "$CURRENT_NOTE" \
    "$CURRENT_LAST_ERROR" \
    "$CURRENT_EXIT_CODE"
}

handle_exit() {
  local rc="$1"
  if (( FINALIZED )); then
    return 0
  fi
  if (( rc == 0 )); then
    return 0
  fi
  update_status \
    "failed" \
    "$CURRENT_PHASE" \
    "$CURRENT_PHASE_LABEL" \
    "$CURRENT_PHASE_CURRENT" \
    "$CURRENT_PHASE_TOTAL" \
    "$CURRENT_OVERALL_CURRENT" \
    "$OVERALL_TOTAL" \
    "$CURRENT_NAME" \
    "$CURRENT_DETAIL" \
    "${CURRENT_NOTE:-failed}" \
    "${CURRENT_LAST_ERROR:-unexpected_exit}" \
    "$rc"
}

trap 'handle_exit $?' EXIT

bucket_for_name() {
  local name="$1" first upper
  first="$(printf '%s' "$name" | sed 's/^[[:space:]]*//; s/^\(.\).*$/\1/')"
  upper="$(printf '%s' "$first" | tr '[:lower:]' '[:upper:]')"
  case "$upper" in
    [0-9]) printf '0-9\n' ;;
    [A-Z]) printf '%s\n' "$upper" ;;
    *) printf '#\n' ;;
  esac
}

rsync_copy() {
  local source="$1" dest="$2"
  if [[ -d "$source" ]]; then
    mkdir -p "$dest"
    "$RSYNC_BIN" -a --inplace --partial --human-readable --info=stats1,name0 "$source"/ "$dest"/
  else
    mkdir -p "$(dirname "$dest")"
    "$RSYNC_BIN" -a --inplace --partial --human-readable --info=stats1,name0 "$source" "$dest"
  fi
}

count_entries() {
  if [[ ! -d "$1" ]]; then
    printf '0\n'
    return 0
  fi
  find "$1" -mindepth 1 -maxdepth 1 \( -type d -o -type f \) | wc -l | tr -d '[:space:]'
}

normalize_title_fragment() {
  local raw="$1"
  printf '%s' "$raw" \
    | sed -E "s/\.dup\.[0-9]+$//; s/\[[^][]+\]//g; s/[._]+/ /g; s/[[:space:]]+/ /g; s/^[[:space:]-]+//; s/[[:space:]-]+$//"
}

requested_basename_stem() {
  local source_entry="$1" name
  name="$(basename "$source_entry")"
  if [[ -f "$source_entry" ]]; then
    name="${name%.*}"
  fi
  normalize_title_fragment "$name"
}

requested_daily_pattern() {
  local value="$1"
  [[ "$value" =~ (^|[-[:space:]])([12][0-9]{3})[[:space:]_.-](0[1-9]|1[0-2])[[:space:]_.-](0[1-9]|[12][0-9]|3[01])($|[-[:space:]]) ]]
}

requested_episode_pattern() {
  local value="$1"
  [[ "$value" =~ (^|[-[:space:]])[Ss][0-9]{1,2}[Ee][0-9]{1,2}($|[-[:space:]]) ]]
}

requested_tv_title_for_entry() {
  local source_entry="$1" stem show
  stem="$(requested_basename_stem "$source_entry")"
  show="$stem"
  if [[ "$show" =~ ^(.*)[-[:space:]]+Season[[:space:]]+[0-9]+($|[-[:space:]]) ]]; then
    show="${BASH_REMATCH[1]}"
  elif [[ "$show" =~ ^(.*?)([-[:space:]]+[Ss][0-9]{1,2}[Ee][0-9]{1,2})($|[-[:space:]]) ]]; then
    show="${BASH_REMATCH[1]}"
  elif requested_daily_pattern "$show"; then
    show="${show%% ${BASH_REMATCH[2]}*}"
  fi
  normalize_title_fragment "$show"
}

requested_movie_title_for_entry() {
  local source_entry="$1" stem title year
  stem="$(requested_basename_stem "$source_entry")"
  if [[ "$stem" =~ ^(.*?)[-[:space:]]+((19|20)[0-9]{2})($|[-[:space:]]) ]]; then
    title="$(normalize_title_fragment "${BASH_REMATCH[1]}")"
    year="${BASH_REMATCH[2]}"
    if [[ -n "$title" ]]; then
      printf '%s (%s)\n' "$title" "$year"
      return 0
    fi
  fi
  normalize_title_fragment "$stem"
}

requested_entry_type() {
  local source_entry="$1" name
  case "$source_entry" in
    "$REQUESTED_MOVIES_SOURCE"/*) printf 'movie\n'; return 0 ;;
    "$REQUESTED_TV_SOURCE"/*) printf 'tv\n'; return 0 ;;
  esac

  name="$(requested_basename_stem "$source_entry")"
  if requested_episode_pattern "$name" || requested_daily_pattern "$name" || [[ "$name" == *" Season "* ]]; then
    printf 'tv\n'
    return 0
  fi
  if [[ -d "$source_entry" ]]; then
    if find "$source_entry" -maxdepth 3 \( -type d -iname 'Season *' -o -type f -iregex '.*[._ -][Ss][0-9]+[Ee][0-9]+.*' \) -print -quit | grep -q .; then
      printf 'tv\n'
      return 0
    fi
  fi
  printf 'movie\n'
}

requested_dest_entry() {
  local source_entry="$1" media_type title bucket name
  media_type="$(requested_entry_type "$source_entry")"
  name="$(basename "$source_entry")"
  if [[ "$media_type" == "tv" ]]; then
    title="$(requested_tv_title_for_entry "$source_entry")"
    bucket="$(bucket_for_name "$title")"
    if [[ -d "$source_entry" ]]; then
      if [[ "$(normalize_title_fragment "$name")" == "$title" ]]; then
        printf '%s/%s/%s\n' "$TV_DEST" "$bucket" "$title"
      else
        printf '%s/%s/%s/%s\n' "$TV_DEST" "$bucket" "$title" "$name"
      fi
    else
      printf '%s/%s/%s/%s\n' "$TV_DEST" "$bucket" "$title" "$name"
    fi
    return 0
  fi

  title="$(requested_movie_title_for_entry "$source_entry")"
  bucket="$(bucket_for_name "$title")"
  if [[ -d "$source_entry" ]]; then
    printf '%s/%s/%s\n' "$MOVIES_DEST" "$bucket" "$title"
  else
    printf '%s/%s/%s/%s\n' "$MOVIES_DEST" "$bucket" "$title" "$name"
  fi
}

sync_bucketed_tree() {
  local source_root="$1" dest_root="$2" label="$3" phase_key="$4" overall_base="$5" overall_total="$6"
  local total=0 current=0 source_entry name bucket dest_entry

  [[ -d "$source_root" ]] || {
    log "$label source missing: $source_root"
    update_status "running" "$phase_key" "$label" 0 0 "$overall_base" "$overall_total" "" "" "source missing"
    return 0
  }

  total="$(count_entries "$source_root")"
  update_status "running" "$phase_key" "$label" 0 "$total" "$overall_base" "$overall_total" "" "" "syncing"
  log "syncing $label from $source_root into bucketed destination $dest_root (entries=$total)"

  while IFS= read -r -d '' source_entry; do
    current=$(( current + 1 ))
    name="$(basename "$source_entry")"
    bucket="$(bucket_for_name "$name")"
    dest_entry="$dest_root/$bucket/$name"
    if (( current == 1 || current % 25 == 0 || current == total )); then
      log "$label progress ${current}/${total}: $name -> $bucket"
      update_status "running" "$phase_key" "$label" "$current" "$total" "$(( overall_base + current ))" "$overall_total" "$name" "$bucket" "syncing"
    fi
    rsync_copy "$source_entry" "$dest_entry"
  done < <(find "$source_root" -mindepth 1 -maxdepth 1 \( -type d -o -type f \) -print0 | sort -z)

  update_status "running" "$phase_key" "$label" "$total" "$total" "$(( overall_base + total ))" "$overall_total" "" "" "phase complete"
}

sync_requested_entries_from_root() {
  local source_root="$1" label="$2" phase_key="$3" overall_base="$4" overall_total="$5"
  local total=0 current=0 source_entry dest_entry media_type

  [[ -d "$source_root" ]] || {
    log "$label source missing: $source_root"
    update_status "running" "$phase_key" "$label" 0 0 "$overall_base" "$overall_total" "" "" "source missing"
    return 0
  }

  total="$(count_entries "$source_root")"
  update_status "running" "$phase_key" "$label" 0 "$total" "$overall_base" "$overall_total" "" "" "syncing"
  log "syncing $label from $source_root into classified destination trees (entries=$total)"

  while IFS= read -r -d '' source_entry; do
    current=$(( current + 1 ))
    media_type="$(requested_entry_type "$source_entry")"
    dest_entry="$(requested_dest_entry "$source_entry")"
    if (( current == 1 || current % 25 == 0 || current == total )); then
      log "$label progress ${current}/${total}: $(basename "$source_entry") -> $media_type"
      update_status "running" "$phase_key" "$label" "$current" "$total" "$(( overall_base + current ))" "$overall_total" "$(basename "$source_entry")" "$media_type" "syncing"
    fi
    rsync_copy "$source_entry" "$dest_entry"
  done < <(find "$source_root" -mindepth 1 -maxdepth 1 \( -type d -o -type f \) -print0 | sort -z)

  update_status "running" "$phase_key" "$label" "$total" "$total" "$(( overall_base + total ))" "$overall_total" "" "" "phase complete"
}

sync_requested_tree() {
  local overall_base="$1" overall_total="$2"
  [[ -d "$REQUESTED_ROOT" ]] || {
    log "requested root missing: $REQUESTED_ROOT"
    update_status "running" "requested" "Requested" 0 0 "$overall_base" "$overall_total" "" "" "requested root missing"
    return 0
  }

  local requested_movies_total requested_tv_total requested_unsorted_total
  requested_movies_total="$(count_entries "$REQUESTED_MOVIES_SOURCE")"
  requested_tv_total="$(count_entries "$REQUESTED_TV_SOURCE")"
  requested_unsorted_total="$(count_entries "$REQUESTED_UNSORTED_SOURCE")"

  sync_requested_entries_from_root "$REQUESTED_MOVIES_SOURCE" "Requested Movies" "requested_movies" "$overall_base" "$overall_total"
  sync_requested_entries_from_root "$REQUESTED_TV_SOURCE" "Requested TV" "requested_tv" "$(( overall_base + requested_movies_total ))" "$overall_total"
  sync_requested_entries_from_root "$REQUESTED_UNSORTED_SOURCE" "Requested Unsorted" "requested_unsorted" "$(( overall_base + requested_movies_total + requested_tv_total ))" "$overall_total"
  sync_requested_entries_from_root "$REQUESTED_INBOX_SOURCE" "Requested Inbox" "requested_inbox" "$(( overall_base + requested_movies_total + requested_tv_total + requested_unsorted_total ))" "$overall_total"
}

main() {
  require_command "$RSYNC_BIN"
  require_command "$PYTHON_BIN"
  require_command timeout

  update_status "running" "init" "Initializing" 0 0 0 0 "" "" "probing mounts"
  probe_dir "$PCLOUD_ROOT" || fail "pcloud plex root not readable: $PCLOUD_ROOT"
  probe_dir "$INTERNXT_ROOT" || fail "internxt plex root not readable: $INTERNXT_ROOT"

  mkdir -p "$MOVIES_DEST" "$TV_DEST"

  local movies_total tv_total requested_movies_total requested_tv_total requested_unsorted_total requested_inbox_total
  movies_total="$(count_entries "$MOVIES_SOURCE")"
  tv_total="$(count_entries "$TV_SOURCE")"
  requested_movies_total="$(count_entries "$REQUESTED_MOVIES_SOURCE")"
  requested_tv_total="$(count_entries "$REQUESTED_TV_SOURCE")"
  requested_unsorted_total="$(count_entries "$REQUESTED_UNSORTED_SOURCE")"
  requested_inbox_total="$(count_entries "$REQUESTED_INBOX_SOURCE")"
  OVERALL_TOTAL=$(( movies_total + tv_total + requested_movies_total + requested_tv_total + requested_unsorted_total + requested_inbox_total ))

  update_status "running" "init" "Initializing" 0 0 0 "$OVERALL_TOTAL" "" "" "starting sync"
  sync_bucketed_tree "$MOVIES_SOURCE" "$MOVIES_DEST" "Movies" "movies" 0 "$OVERALL_TOTAL"
  sync_bucketed_tree "$TV_SOURCE" "$TV_DEST" "TV" "tv" "$movies_total" "$OVERALL_TOTAL"
  sync_requested_tree "$(( movies_total + tv_total ))" "$OVERALL_TOTAL"

  FINALIZED=1
  update_status "completed" "complete" "Completed" "$OVERALL_TOTAL" "$OVERALL_TOTAL" "$OVERALL_TOTAL" "$OVERALL_TOTAL" "" "" "plex internxt mirror run completed"
  log "plex internxt mirror run completed"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
