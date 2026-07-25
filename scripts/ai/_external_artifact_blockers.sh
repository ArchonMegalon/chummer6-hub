#!/usr/bin/env bash

EXTERNAL_RELEASE_BLOCKER_COUNT=0
EXTERNAL_RELEASE_BLOCKERS=""

record_external_release_blocker() {
  local blocker="$1"
  EXTERNAL_RELEASE_BLOCKER_COUNT=$((EXTERNAL_RELEASE_BLOCKER_COUNT + 1))
  if [[ -n "$EXTERNAL_RELEASE_BLOCKERS" ]]; then
    EXTERNAL_RELEASE_BLOCKERS="${EXTERNAL_RELEASE_BLOCKERS}"$'\n'
  fi
  EXTERNAL_RELEASE_BLOCKERS="${EXTERNAL_RELEASE_BLOCKERS}- ${blocker}"
}

run_expected_external_artifact_gate() {
  local blocker="$1"
  local expected_wait_marker="$2"
  shift 2

  local gate_log
  local gate_status
  gate_log="$(mktemp)"

  if "$@" >"$gate_log" 2>&1; then
    cat "$gate_log"
    rm -f "$gate_log"
    return 0
  else
    gate_status=$?
  fi

  cat "$gate_log" >&2
  if [[ "$gate_status" -eq 2 ]] && grep -Fq "$expected_wait_marker" "$gate_log"; then
    record_external_release_blocker "$blocker"
    rm -f "$gate_log"
    return 0
  fi

  rm -f "$gate_log"
  return "$gate_status"
}

fail_on_external_release_blockers() {
  if [[ "$EXTERNAL_RELEASE_BLOCKER_COUNT" -eq 0 ]]; then
    return 0
  fi

  echo "verify completed local/self-hosted gates but release remains blocked by ${EXTERNAL_RELEASE_BLOCKER_COUNT} external artifact(s):" >&2
  printf '%s\n' "$EXTERNAL_RELEASE_BLOCKERS" >&2
  return 2
}
