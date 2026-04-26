#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
bootstrap_path="$repo_root/Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh"
bootstrap_url="${CHUMMER_BOOTSTRAP_URL:-https://chummer.run/downloads/release-upload/bootstrap.sh}"
bootstrap_command_url="${CHUMMER_BOOTSTRAP_COMMAND_URL:-${bootstrap_url%/bootstrap.sh}/bootstrap.command}"

RELEASE_UPLOAD_TOKEN="${CHUMMER_RELEASE_UPLOAD_TOKEN:-}"
RELEASE_UPLOAD_TOKEN_FILE="${CHUMMER_RELEASE_UPLOAD_TOKEN_FILE:-${CHUMMER_RELEASE_UPLOAD_TOKEN_PATH:-}}"
RELEASE_UPLOAD_TICKET="${CHUMMER_RELEASE_UPLOAD_TICKET:-}"
RELEASE_UPLOAD_TICKET_FILE="${CHUMMER_RELEASE_UPLOAD_TICKET_FILE:-${CHUMMER_RELEASE_UPLOAD_TICKET_PATH:-}}"
FORCE_LOCAL_BOOTSTRAP="${CHUMMER_BOOTSTRAP_FORCE_LOCAL:-0}"

trim_auth_value() {
  local value="$1"
  printf '%s' "${value#"${value%%[![:space:]]*}"}" | tr -d '\r\n'
}

resolve_auth_file_value() {
  local file_path="$1"
  [[ -n "$file_path" ]] || return 1
  [[ -f "$file_path" ]] || return 1

  local value
  value="$(sed -n '1p' "$file_path")"
  value="$(trim_auth_value "$value")"
  [[ -n "$value" ]] || return 1
  printf '%s' "$value"
}

resolve_release_upload_auth() {
  local token
  local ticket

  token="$(trim_auth_value "${RELEASE_UPLOAD_TOKEN}")"
  if [[ -z "$token" ]]; then
    token="$(resolve_auth_file_value "$RELEASE_UPLOAD_TOKEN_FILE" || true)"
  fi
  if [[ -n "$token" ]]; then
    printf '%s\napi_token\n' "$token"
    return 0
  fi

  ticket="$(trim_auth_value "${RELEASE_UPLOAD_TICKET}")"
  if [[ -z "$ticket" ]]; then
    ticket="$(resolve_auth_file_value "$RELEASE_UPLOAD_TICKET_FILE" || true)"
  fi
  if [[ -n "$ticket" ]]; then
    printf '%s\nticket\n' "$ticket"
    return 0
  fi

  return 1
}

url_encode() {
  python3 - "$1" <<'PY'
from __future__ import annotations

import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""))
PY
}

if [[ "$FORCE_LOCAL_BOOTSTRAP" == "1" ]] && [[ -f "$bootstrap_path" ]]; then
  local_auth_bootstrap=1
else
  local_auth_bootstrap=0
fi

auth_pair="$(resolve_release_upload_auth || true)"
auth_value="${auth_pair%%$'\n'*}"
auth_mode="${auth_pair#*$'\n'}"

if [[ "$local_auth_bootstrap" -eq 1 ]]; then
  case "${auth_mode}" in
    api_token)
      exec env "CHUMMER_RELEASE_UPLOAD_TOKEN=$auth_value" bash "$bootstrap_path" "$@"
      ;;
    ticket)
      exec env "CHUMMER_RELEASE_UPLOAD_TICKET=$auth_value" bash "$bootstrap_path" "$@"
      ;;
    *)
      cat >&2 <<'EOF'
[chummer-mac-release-wrapper] ERROR: local bootstrap execution requires CHUMMER_RELEASE_UPLOAD_TOKEN or CHUMMER_RELEASE_UPLOAD_TICKET.

This environment is configured for local script execution. To continue:

  * set CHUMMER_RELEASE_UPLOAD_TOKEN=...
  * set CHUMMER_RELEASE_UPLOAD_TICKET=...
  * point CHUMMER_RELEASE_UPLOAD_TOKEN_FILE or CHUMMER_RELEASE_UPLOAD_TICKET_FILE at a one-line token source

To use the hosted, signed-in command path instead, unset CHUMMER_BOOTSTRAP_FORCE_LOCAL or set it to 0.
EOF
      exit 1
      ;;
  esac
fi

if [[ -z "$auth_mode" ]]; then
  cat >&2 <<'EOF'
[chummer-mac-release-wrapper] ERROR: no release-upload auth was supplied.

This wrapper cannot mint a signed-in release ticket by itself. The zero-extra-env path is:

  1. open https://chummer.run/downloads/release-upload in a signed-in browser
  2. copy the generated Command block
  3. paste that exact command into the Mac release shell

That generated command already carries the short-lived upload ticket, pins the hosted
bootstrap SHA-256, and should not stop later for CHUMMER_RELEASE_UPLOAD_TICKET or
CHUMMER_RELEASE_UPLOAD_TOKEN.

For repo-local automation, set one of these before running the wrapper:

  * CHUMMER_RELEASE_UPLOAD_TOKEN=...
  * CHUMMER_RELEASE_UPLOAD_TICKET=...
  * CHUMMER_RELEASE_UPLOAD_TOKEN_FILE=... (one-line secret file)
  * CHUMMER_RELEASE_UPLOAD_TICKET_FILE=... (one-line ticket file)

Do not run the public bootstrap.sh URL directly for release promotion; it can verify
integrity but it has no upload credential unless the signed-in page or this wrapper
attaches one first.
EOF
  exit 1
fi

bootstrap_url_encoded_auth="$(url_encode "$auth_value")"
if [[ "$auth_mode" == "api_token" ]]; then
  bootstrap_command_url="${bootstrap_command_url}?apiToken=${bootstrap_url_encoded_auth}"
else
  bootstrap_command_url="${bootstrap_command_url}?ticket=${bootstrap_url_encoded_auth}"
fi

tmp_bootstrap="$(mktemp)"
trap 'rm -f "$tmp_bootstrap"' EXIT

curl_options=("--fail")
if curl --help | grep -q -- "--fail-with-body"; then
  curl_options=("--fail-with-body")
fi

curl -fsSL "${curl_options[@]}" "$bootstrap_command_url" -o "$tmp_bootstrap"
chmod 700 "$tmp_bootstrap"
exec bash "$tmp_bootstrap" "$@"
