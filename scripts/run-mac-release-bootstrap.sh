#!/usr/bin/env bash
set +x
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
bootstrap_path="$repo_root/Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh"

STAGE_ONLY="${CHUMMER_MAC_RELEASE_STAGE_ONLY:-}"
STAGE_OUTPUT_DIR="${CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR:-}"

wrapper_die() {
  printf '[chummer-mac-release-wrapper] ERROR: %s\n' "$*" >&2
  exit 1
}

parse_stage_only_args() {
  local env_mode="$STAGE_ONLY"
  local env_output="$STAGE_OUTPUT_DIR"
  local flag_mode=0
  local flag_output=""
  local normalized=""

  if [[ -n "$env_mode" ]]; then
    normalized="$(printf '%s' "$env_mode" | tr '[:upper:]' '[:lower:]')"
    case "$normalized" in
      1|true|yes|on) STAGE_ONLY=1 ;;
      0|false|no|off) STAGE_ONLY=0 ;;
      *) wrapper_die "CHUMMER_MAC_RELEASE_STAGE_ONLY must be a boolean value" ;;
    esac
  else
    STAGE_ONLY=0
  fi

  while (( $# > 0 )); do
    case "$1" in
      --stage-only)
        flag_mode=1
        shift
        ;;
      --stage-output-dir)
        (( $# >= 2 )) || wrapper_die "--stage-output-dir requires a path"
        [[ -z "$flag_output" ]] || wrapper_die "--stage-output-dir may be supplied only once"
        flag_output="$2"
        shift 2
        ;;
      --stage-output-dir=*)
        [[ -z "$flag_output" ]] || wrapper_die "--stage-output-dir may be supplied only once"
        flag_output="${1#--stage-output-dir=}"
        shift
        ;;
      *)
        shift
        ;;
    esac
  done

  if (( flag_mode == 1 )); then
    if [[ -n "$env_mode" && "$STAGE_ONLY" != "1" ]]; then
      wrapper_die "--stage-only conflicts with CHUMMER_MAC_RELEASE_STAGE_ONLY=$env_mode"
    fi
    STAGE_ONLY=1
  fi
  if [[ -n "$flag_output" && -n "$env_output" && "$flag_output" != "$env_output" ]]; then
    wrapper_die "--stage-output-dir conflicts with CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR"
  fi
  STAGE_OUTPUT_DIR="${flag_output:-$env_output}"

  if [[ "$STAGE_ONLY" != "1" ]]; then
    [[ -z "$STAGE_OUTPUT_DIR" ]] \
      || wrapper_die "--stage-output-dir/CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR requires stage-only mode"
    return 0
  fi
  [[ -n "$STAGE_OUTPUT_DIR" ]] \
    || wrapper_die "stage-only mode requires --stage-output-dir or CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR"

  [[ -z "${CHUMMER_RELEASE_UPLOAD_TOKEN:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_TOKEN"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_TOKEN_FILE:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_TOKEN_FILE"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_TOKEN_PATH:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_TOKEN_PATH"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_TICKET:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_TICKET"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_TICKET_FILE:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_TICKET_FILE"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_TICKET_PATH:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_TICKET_PATH"
  [[ -z "${FLEET_INTERNAL_API_TOKEN:-}" ]] || wrapper_die "stage-only mode rejects FLEET_INTERNAL_API_TOKEN"
  [[ -z "${CHUMMER_RELEASE_PUBLISH_MODE:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_PUBLISH_MODE"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_URL:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_URL"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_SESSIONS_URL:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_SESSIONS_URL"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_MAX_ATTEMPTS:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_MAX_ATTEMPTS"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_RETRY_SLEEP_SECONDS:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_RETRY_SLEEP_SECONDS"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_DIRECT_LIMIT_BYTES:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_DIRECT_LIMIT_BYTES"
  [[ -z "${CHUMMER_RELEASE_UPLOAD_CHUNK_BYTES:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_CHUNK_BYTES"
  [[ -z "${CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE"
  [[ -z "${CHUMMER_RELEASE_PRINT_SIGNED_INSTALL_CLAIMS:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_PRINT_SIGNED_INSTALL_CLAIMS"
  [[ -z "${CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION"
  [[ -z "${CHUMMER_RELEASE_SKIP_STRICT_MANIFEST_VERIFY:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_SKIP_STRICT_MANIFEST_VERIFY"
  [[ -z "${CHUMMER_RELEASE_SSH_TARGET:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_RELEASE_SSH_TARGET"
  [[ -z "${CHUMMER_REMOTE_STAGING_DIR:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_REMOTE_STAGING_DIR"
  [[ -z "${CHUMMER_REMOTE_UI_REPO_DIR:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_REMOTE_UI_REPO_DIR"
  [[ -z "${CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR"
  [[ -z "${CHUMMER_PORTAL_DOWNLOADS_S3_URI:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_PORTAL_DOWNLOADS_S3_URI"
  [[ -z "${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL"
  [[ -z "${CHUMMER_APP_SIGN_IDENTITY:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_APP_SIGN_IDENTITY"
  [[ -z "${CHUMMER_NOTARY_PROFILE:-}" ]] || wrapper_die "stage-only mode rejects CHUMMER_NOTARY_PROFILE"
}

parse_stage_only_args "$@"

if [[ "$STAGE_ONLY" == "1" ]]; then
  [[ -f "$bootstrap_path" ]] || wrapper_die "local bootstrap is missing: $bootstrap_path"
  exec env \
    "CHUMMER_MAC_RELEASE_STAGE_ONLY=1" \
    "CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR=$STAGE_OUTPUT_DIR" \
    bash "$bootstrap_path" "$@"
fi

if [[
  -n "${CHUMMER_RELEASE_UPLOAD_TOKEN:-}"
  || -n "${CHUMMER_RELEASE_UPLOAD_TICKET:-}"
  || -n "${CHUMMER_RELEASE_UPLOAD_TOKEN_FILE:-}"
  || -n "${CHUMMER_RELEASE_UPLOAD_TOKEN_PATH:-}"
  || -n "${CHUMMER_RELEASE_UPLOAD_TICKET_FILE:-}"
  || -n "${CHUMMER_RELEASE_UPLOAD_TICKET_PATH:-}"
]]; then
  [[ -f "$bootstrap_path" && ! -L "$bootstrap_path" ]] \
    || wrapper_die "local bootstrap is missing or unsafe: $bootstrap_path"
  exec bash "$bootstrap_path" "$@"
fi

cat >&2 <<'EOF'
[chummer-mac-release-wrapper] ERROR: no release-upload auth was supplied.

This wrapper cannot mint a signed-in release ticket by itself. The zero-extra-env path is:

  1. open https://chummer.run/downloads/release-upload in a signed-in browser
  2. copy the generated Command block
  3. paste that exact command into the Mac release shell

That signed-in command pins the hosted bootstrap SHA-256 and prompts for the short-lived
access code (or reads `CHUMMER_RELEASE_UPLOAD_TICKET_FILE`) without putting a credential
in a request URL or process argument.

For repo-local automation, set exactly one of these before running the wrapper:

  * CHUMMER_RELEASE_UPLOAD_TOKEN=...
  * CHUMMER_RELEASE_UPLOAD_TICKET=...
  * CHUMMER_RELEASE_UPLOAD_TOKEN_FILE=... (one-line secret file)
  * CHUMMER_RELEASE_UPLOAD_TOKEN_PATH=... (alias of TOKEN_FILE)
  * CHUMMER_RELEASE_UPLOAD_TICKET_FILE=... (one-line ticket file)
  * CHUMMER_RELEASE_UPLOAD_TICKET_PATH=... (alias of TICKET_FILE)

This repository wrapper executes only its checked-out local bootstrap. It never appends
release credentials to `bootstrap.command`, `bootstrap.sh`, or any other request URL.
EOF
exit 1
