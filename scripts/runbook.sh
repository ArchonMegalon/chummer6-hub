#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -z "${COMPOSE_FILE:-}" ]]; then
  COMPOSE_FILE="$REPO_ROOT/legacy/tooling/docker/docker-compose.yml"
  if [[ "${CHUMMER_RUNBOOK_INCLUDE_LOCAL_COMPOSE_OVERRIDE:-0}" == "1" && -f "$REPO_ROOT/legacy/tooling/docker/docker-compose.override.yml" ]]; then
    COMPOSE_FILE="${COMPOSE_FILE}:$REPO_ROOT/legacy/tooling/docker/docker-compose.override.yml"
  fi
  export COMPOSE_FILE
fi

RUNBOOK_MODE="${RUNBOOK_MODE:-${1:-tunnel}}"
RUNBOOK_ARG_FRAMEWORK="${2:-}"
RUNBOOK_ARG_FILTER="${3:-}"
TUNNEL_CONTAINER="${TUNNEL_CONTAINER:-cloudflared_v2}"
DOCKER_NETWORK="${DOCKER_NETWORK:-arr_net_v2}"
UPSTREAM_PRIMARY="${UPSTREAM_PRIMARY:-http://172.17.0.1:8088}"
UPSTREAM_UI="${UPSTREAM_UI:-http://172.17.0.1:8089}"
UPSTREAM_LEGACY="${UPSTREAM_LEGACY:-http://chummer-web:8080}"
UPSTREAM_UI_SERVICE="${UPSTREAM_UI_SERVICE:-http://chummer-blazor:8080}"
UPSTREAM_HOST_INTERNAL="${UPSTREAM_HOST_INTERNAL:-http://host.docker.internal:8088}"

if ! command -v rg >/dev/null 2>&1; then
  echo "ripgrep (rg) is required for this runbook." >&2
  exit 1
fi

resolve_ui_localization_release_gate_path() {
  local explicit_path="${CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH:-}"
  if [[ -n "$explicit_path" ]]; then
    echo "$explicit_path"
    return 0
  fi

  local candidate
  for candidate in \
    "$REPO_ROOT/Chummer.Run.Api/wwwroot/proofs/mac-codex-release/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "$REPO_ROOT/../chummer6-ui/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "$REPO_ROOT/../chummer6-ui-finish/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "$REPO_ROOT/../chummer-presentation-clean/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "$REPO_ROOT/../chummer-presentation/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "/docker/chummercomplete/chummer6-ui/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "/docker/chummercomplete/chummer6-ui-finish/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "/docker/chummercomplete/chummer-presentation-clean/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json" \
    "/docker/chummercomplete/chummer-presentation/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json"
  do
    if [[ -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  echo "$REPO_ROOT/Chummer.Run.Api/wwwroot/proofs/mac-codex-release/UI_LOCALIZATION_RELEASE_GATE.generated.json"
}

run_compose_with_optional_env_file() {
  local env_file="$REPO_ROOT/.env"
  if [[ -f "$env_file" ]]; then
    docker compose --env-file "$env_file" "$@"
  else
    docker compose "$@"
  fi
}

ensure_hub_cloudflare_tunnel() {
  local env_file="$REPO_ROOT/.env"
  local log_file="${1:-/dev/null}"
  local token_available=0
  if [[ -f "$env_file" ]] && rg -q '^CHUMMER_RUN_CF_TUNNEL_TOKEN=.+' "$env_file"; then
    token_available=1
  elif [[ -n "${CHUMMER_RUN_CF_TUNNEL_TOKEN:-}" ]]; then
    token_available=1
  fi

  if [[ "$token_available" -ne 1 ]]; then
    echo "hub live audit: CHUMMER_RUN_CF_TUNNEL_TOKEN is unavailable; skipping tunnel bootstrap." | tee -a "$log_file" >/dev/null
    return 0
  fi

  local compose_file="$REPO_ROOT/legacy/tooling/docker/docker-compose.yml"
  local tunnel_log
  tunnel_log="$(mktemp)"
  set +e
  run_compose_with_optional_env_file -f "$compose_file" --profile portal up -d chummer-run-cloudflared 2>&1 | tee "$tunnel_log"
  local status=${PIPESTATUS[0]}
  set -e
  cat "$tunnel_log" >> "$log_file" 2>/dev/null || true
  if [[ "$status" -ne 0 ]]; then
    rm -f "$tunnel_log"
    return "$status"
  fi
  rm -f "$tunnel_log"
  TUNNEL_CONTAINER="chummer-run-cloudflared"
  export TUNNEL_CONTAINER
}

resolve_runbook_log_file() {
  local base_name="$1"
  local uid_suffix
  uid_suffix="$(id -u 2>/dev/null || echo user)"
  local candidates=()
  if [[ -n "${RUNBOOK_LOG_DIR:-}" ]]; then
    candidates+=("${RUNBOOK_LOG_DIR}/${base_name}.${uid_suffix}.log")
  fi
  if [[ -n "${XDG_RUNTIME_DIR:-}" ]]; then
    candidates+=("${XDG_RUNTIME_DIR}/${base_name}.${uid_suffix}.log")
  fi
  if [[ -n "${TMPDIR:-}" ]]; then
    candidates+=("${TMPDIR}/${base_name}.${uid_suffix}.log")
  fi
  candidates+=("$REPO_ROOT/.tmp/${base_name}.${uid_suffix}.log")
  if [[ -n "${HOME:-}" ]]; then
    candidates+=("${HOME}/.cache/chummer/${base_name}.${uid_suffix}.log")
  fi
  candidates+=("$REPO_ROOT/${base_name}.${uid_suffix}.log")

  for candidate in "${candidates[@]}"; do
    local dir
    dir="$(dirname "$candidate")"
    if mkdir -p "$dir" 2>/dev/null && touch "$candidate" 2>/dev/null; then
      echo "$candidate"
      return 0
    fi
  done

  echo "/dev/null"
}

resolve_runbook_dir() {
  local base_name="$1"
  local candidates=()
  if [[ -n "${RUNBOOK_STATE_DIR:-}" ]]; then
    candidates+=("${RUNBOOK_STATE_DIR}/${base_name}")
  fi
  if [[ -n "${XDG_STATE_HOME:-}" ]]; then
    candidates+=("${XDG_STATE_HOME}/chummer/${base_name}")
  fi
  if [[ -n "${XDG_CACHE_HOME:-}" ]]; then
    candidates+=("${XDG_CACHE_HOME}/chummer/${base_name}")
  fi
  candidates+=("$REPO_ROOT/.tmp/${base_name}")
  if [[ -n "${HOME:-}" ]]; then
    candidates+=("${HOME}/.cache/chummer/${base_name}")
  fi

  for candidate in "${candidates[@]}"; do
    if mkdir -p "$candidate" 2>/dev/null && [[ -w "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  echo "$REPO_ROOT/.tmp/${base_name}"
}

if [[ "$RUNBOOK_MODE" == "migration" ]]; then
  LOOPS="${MIGRATION_LOOPS:-1}"
  LOG_FILE="${RUNBOOK_LOG_FILE:-$(resolve_runbook_log_file migration-loop-runbook)}"
  set +e
  bash scripts/migration-loop.sh "$LOOPS" 2>&1 | tee "$LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== migration failure extract =="
  rg -n "Failed|failed|\\[xUnit.net\\]|error|Test summary|Stack Trace" "$LOG_FILE" | tail -n 200 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "local-tests" ]]; then
  TEST_PROJECT="${TEST_PROJECT:-Chummer.Tests/Chummer.Tests.csproj}"
  TEST_CONFIGURATION="${TEST_CONFIGURATION:-Release}"
  TEST_FRAMEWORK="${TEST_FRAMEWORK:-$RUNBOOK_ARG_FRAMEWORK}"
  TEST_FILTER="${TEST_FILTER:-$RUNBOOK_ARG_FILTER}"
  TEST_MAX_CPU="${TEST_MAX_CPU:-1}"
  TEST_DISABLE_BUILD_SERVERS="${TEST_DISABLE_BUILD_SERVERS:-1}"
  TEST_NO_RESTORE="${TEST_NO_RESTORE:-0}"
  TEST_NO_BUILD="${TEST_NO_BUILD:-0}"
  TEST_NUGET_PREFLIGHT="${TEST_NUGET_PREFLIGHT:-1}"
  TEST_NUGET_SOFT_FAIL="${TEST_NUGET_SOFT_FAIL:-}"
  TEST_NUGET_ENDPOINT="${TEST_NUGET_ENDPOINT:-api.nuget.org:443}"
  TEST_LOG_FILE="${TEST_LOG_FILE:-$(resolve_runbook_log_file chummer-local-tests)}"
  export DOTNET_CLI_HOME="${DOTNET_CLI_HOME:-$(resolve_runbook_dir dotnet-cli-home)}"
  export DOTNET_NOLOGO="${DOTNET_NOLOGO:-1}"
  export DOTNET_SKIP_FIRST_TIME_EXPERIENCE="${DOTNET_SKIP_FIRST_TIME_EXPERIENCE:-1}"
  export DOTNET_CLI_TELEMETRY_OPTOUT="${DOTNET_CLI_TELEMETRY_OPTOUT:-1}"
  export AVALONIA_TELEMETRY_OPTOUT="${AVALONIA_TELEMETRY_OPTOUT:-1}"
  export DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER="${DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER:-1}"
  export MSBUILDDISABLENODEREUSE="${MSBUILDDISABLENODEREUSE:-1}"
  if [[ -z "${CHUMMER_API_BASE_URL:-}" ]] && command -v docker >/dev/null 2>&1; then
    set +e
    detected_api_binding="$(docker compose port chummer-api 8080 2>/dev/null | tail -n 1)"
    detected_api_status=$?
    set -e
    if [[ "$detected_api_status" -eq 0 && -n "$detected_api_binding" ]]; then
      detected_api_port="${detected_api_binding##*:}"
      if [[ "$detected_api_port" =~ ^[0-9]+$ ]]; then
        export CHUMMER_API_BASE_URL="http://127.0.0.1:${detected_api_port}"
      fi
    fi
  fi
  framework_args=()
  filter_args=()
  cpu_args=()
  server_args=()
  restore_args=()
  build_args=()
  if [[ -z "$TEST_NUGET_SOFT_FAIL" ]]; then
    if [[ "${CI:-}" == "true" || "${CI:-}" == "1" ]]; then
      TEST_NUGET_SOFT_FAIL=0
    else
      TEST_NUGET_SOFT_FAIL=1
    fi
  fi
  if [[ -n "$TEST_FRAMEWORK" ]]; then
    framework_args=(-f "$TEST_FRAMEWORK")
  fi
  if [[ -n "$TEST_FILTER" ]]; then
    filter_args=(--filter "$TEST_FILTER")
  fi
  if [[ -n "$TEST_MAX_CPU" ]]; then
    cpu_args=(-m:"$TEST_MAX_CPU")
  fi
  if [[ "$TEST_DISABLE_BUILD_SERVERS" == "1" || "$TEST_DISABLE_BUILD_SERVERS" == "true" || "$TEST_DISABLE_BUILD_SERVERS" == "TRUE" ]]; then
    server_args=(--disable-build-servers)
  fi
  if [[ "$TEST_NO_RESTORE" == "1" || "$TEST_NO_RESTORE" == "true" || "$TEST_NO_RESTORE" == "TRUE" ]]; then
    restore_args=(--no-restore)
  fi
  if [[ "$TEST_NO_BUILD" == "1" || "$TEST_NO_BUILD" == "true" || "$TEST_NO_BUILD" == "TRUE" ]]; then
    build_args=(--no-build)
  fi
  if [[ "$TEST_NO_RESTORE" != "1" && "$TEST_NO_RESTORE" != "true" && "$TEST_NO_RESTORE" != "TRUE" ]]; then
    if [[ "$TEST_NUGET_PREFLIGHT" == "1" || "$TEST_NUGET_PREFLIGHT" == "true" || "$TEST_NUGET_PREFLIGHT" == "TRUE" ]]; then
      host="${TEST_NUGET_ENDPOINT%:*}"
      port="${TEST_NUGET_ENDPOINT##*:}"
      if [[ -z "$host" || -z "$port" || "$host" == "$port" ]]; then
        echo "Invalid TEST_NUGET_ENDPOINT value: '$TEST_NUGET_ENDPOINT' (expected host:port)." >&2
        exit 1
      fi
      set +e
      python3 - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.create_connection((host, port), timeout=3):
    pass
PY
      preflight_status=$?
      set -e
      if [[ "$preflight_status" -ne 0 ]]; then
        if [[ "$TEST_NUGET_SOFT_FAIL" == "1" || "$TEST_NUGET_SOFT_FAIL" == "true" || "$TEST_NUGET_SOFT_FAIL" == "TRUE" ]]; then
          echo "skipping local-tests due NuGet preflight failure for $TEST_NUGET_ENDPOINT (set TEST_NUGET_SOFT_FAIL=0 to enforce failure)." >&2
          exit 0
        fi
        echo "NuGet preflight failed for $TEST_NUGET_ENDPOINT; set TEST_NO_RESTORE=1 for offline assets or enable outbound network." >&2
        exit 1
      fi
    fi
  fi
  if [[ -n "${CHUMMER_API_BASE_URL:-}" ]]; then
    echo "local-tests using CHUMMER_API_BASE_URL=$CHUMMER_API_BASE_URL"
  fi
  set +e
  dotnet test "$TEST_PROJECT" -c "$TEST_CONFIGURATION" "${framework_args[@]}" "${filter_args[@]}" "${cpu_args[@]}" "${server_args[@]}" "${restore_args[@]}" "${build_args[@]}" --logger "console;verbosity=normal" 2>&1 | tee "$TEST_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== local test failure extract =="
  rg -n "^\\s*Failed\\s|\\[xUnit.net\\]|Total tests:|Passed!|Failed!|Stack Trace|Error Message" "$TEST_LOG_FILE" | tail -n 200 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "refresh-local-api" ]]; then
  API_REFRESH_LOG_FILE="${API_REFRESH_LOG_FILE:-$(resolve_runbook_log_file chummer-refresh-local-api)}"
  set +e
  docker compose up -d --build chummer-api 2>&1 | tee "$API_REFRESH_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  if [[ "$status" -ne 0 ]]; then
    echo
    echo "== refresh-local-api failure extract =="
    rg -n "error|failed|denied|exception" "$API_REFRESH_LOG_FILE" | tail -n 200 || true
    exit "$status"
  fi

  detected_api_binding="$(docker compose port chummer-api 8080 2>/dev/null | tail -n 1)"
  detected_api_port="${detected_api_binding##*:}"
  if [[ -z "$detected_api_port" || ! "$detected_api_port" =~ ^[0-9]+$ ]]; then
    echo "Unable to resolve chummer-api published port after rebuild." >&2
    exit 1
  fi

  api_probe_url="http://127.0.0.1:${detected_api_port}/api/info"
  python3 - "$api_probe_url" <<'PY'
import sys
import time
import urllib.error
import urllib.request

url = sys.argv[1]
deadline = time.time() + 60
last_error = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            if 200 <= response.status < 500:
                print(url)
                sys.exit(0)
    except Exception as exc:  # pragma: no cover - runbook probe path
        last_error = exc
    time.sleep(1)

print(f"API probe failed for {url}: {last_error}", file=sys.stderr)
sys.exit(1)
PY
  exit 0
fi

if [[ "$RUNBOOK_MODE" == "host-prereqs" ]]; then
  PREREQ_LOG_FILE="${PREREQ_LOG_FILE:-$(resolve_runbook_log_file chummer-host-prereqs)}"
  PREREQ_LOG_DIR="$(dirname "$PREREQ_LOG_FILE")"
  set +e
  PREREQ_LOG_DIR="$PREREQ_LOG_DIR" bash scripts/check-host-gate-prereqs.sh 2>&1 | tee "$PREREQ_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== host prerequisite summary =="
  if [[ "$PREREQ_LOG_FILE" == "/dev/null" ]]; then
    echo "host-prereqs log capture disabled (no writable log path found)."
  else
    rg -n "\\[PASS\\]|\\[FAIL\\]|\\[SKIP\\]|Strict host gates are" "$PREREQ_LOG_FILE" | tail -n 200 || true
  fi
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "desktop-gate" ]]; then
  status=0

  require_path() {
    local path="$1"
    if [[ ! -e "$path" ]]; then
      echo "missing path: $path" >&2
      status=1
    fi
  }

  require_match() {
    local pattern="$1"
    local path="$2"
    if ! rg -q -- "$pattern" "$path"; then
      echo "missing pattern '$pattern' in $path" >&2
      status=1
    fi
  }

  require_no_match() {
    local pattern="$1"
    local path="$2"
    if rg -q -- "$pattern" "$path"; then
      echo "forbidden pattern '$pattern' found in $path" >&2
      status=1
    fi
  }

  require_path "Chummer.Run.Api/Chummer.Run.Api.csproj"
  require_path "Chummer.Run.Api/Program.cs"
  require_path "Chummer.Run.Api/Controllers/PublicLandingController.cs"
  require_path "Chummer.Portal/downloads/releases.json"
  require_path "scripts/validate-amend-manifests.sh"
  require_path "scripts/generate-parity-checklist.sh"
  require_path "scripts/check-host-gate-prereqs.sh"
  require_path "scripts/runbook-strict-host-gates.sh"
  require_path "scripts/publish-download-bundle-http.sh"
  require_path "docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md"
  require_path "docs/ACTIVE_HEAD_RELEASE_ARTIFACTS.md"

  require_match "\\[HttpGet\\(\"/downloads\"\\)\\]" "Chummer.Run.Api/Controllers/PublicLandingController.cs"
  require_match "CHUMMER_DOWNLOADS_SOURCE_ROOT" "docker-compose.public-edge.yml"
  require_match "SELF_HOSTED_DOWNLOADS_RUNBOOK.md" "README.md"
  require_match "chummer-\\*-installer\\.deb" "scripts/generate-releases-manifest.sh"
  require_match "chummer-\\*-installer\\.exe" "scripts/generate-releases-manifest.sh"
  require_match "RUNBOOK_MODE\" == \"downloads-manifest\"" "scripts/runbook.sh"
  require_match "RUNBOOK_MODE\" == \"host-prereqs\"" "scripts/runbook.sh"
  require_match "RUNBOOK_MODE\" == \"downloads-sync\"" "scripts/runbook.sh"
  require_match "RUNBOOK_MODE\" == \"downloads-sync-s3\"" "scripts/runbook.sh"
  require_match "RUNBOOK_MODE\" == \"downloads-upload-http\"" "scripts/runbook.sh"
  require_match "RUNBOOK_MODE\" == \"parity-checklist\"" "scripts/runbook.sh"
  require_match "RUNBOOK_MODE\" == \"amend-checksums\"" "scripts/runbook.sh"
  require_match "bash scripts/generate-releases-manifest.sh" "scripts/runbook.sh"
  require_match "bash scripts/generate-parity-checklist.sh" "scripts/runbook.sh"
  require_match "bash scripts/publish-download-bundle.sh" "scripts/runbook.sh"
  require_match "bash scripts/publish-download-bundle-s3.sh" "scripts/runbook.sh"
  require_match "bash scripts/publish-download-bundle-http.sh" "scripts/runbook.sh"
  require_match "CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR" "docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md"
  require_match "CHUMMER_PORTAL_DOWNLOADS_S3_URI" "docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md"
  require_match "CHUMMER_PORTAL_DOWNLOADS_AWS_ACCESS_KEY_ID" "docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md"
  require_match "CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS" "docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md"
  require_match "DOCKER_TESTS_SOFT_FAIL=0" "scripts/runbook-strict-host-gates.sh"
  require_match "TEST_NUGET_SOFT_FAIL=0" "scripts/runbook-strict-host-gates.sh"
  require_match "RUNBOOK_MODE=docker-tests" "scripts/runbook-strict-host-gates.sh"
  require_match "RUNBOOK_MODE=local-tests" "scripts/runbook-strict-host-gates.sh"
  require_match "check-host-gate-prereqs.sh" "scripts/runbook-strict-host-gates.sh"
  require_match "strict host prerequisite gate" "scripts/runbook-strict-host-gates.sh"
  require_match "Strict host gates are" "scripts/check-host-gate-prereqs.sh"
  require_match "\\[PASS\\]" "scripts/check-host-gate-prereqs.sh"
  require_match "\\[FAIL\\]" "scripts/check-host-gate-prereqs.sh"
  require_match "bash scripts/validate-amend-manifests.sh" "scripts/runbook.sh"
  require_match "legacy/tooling/docker/Docker/Downloads/releases.json" "scripts/generate-releases-manifest.sh"
  require_match "Chummer.Portal/downloads/releases.json" "scripts/generate-releases-manifest.sh"

  if [[ "$status" -ne 0 ]]; then
    echo "desktop-gate checks failed" >&2
    exit "$status"
  fi

  echo "desktop-gate checks passed"
  exit 0
fi

if [[ "$RUNBOOK_MODE" == "desktop-build" ]]; then
  DESKTOP_PROJECT="${DESKTOP_PROJECT:-${RUNBOOK_ARG_FRAMEWORK:-Chummer.Run.Api/Chummer.Run.Api.csproj}}"
  DESKTOP_FRAMEWORK="${DESKTOP_FRAMEWORK:-${RUNBOOK_ARG_FILTER:-net10.0}}"
  DESKTOP_LOG_FILE="${DESKTOP_LOG_FILE:-$(resolve_runbook_log_file chummer-desktop-build)}"
  set +e
  docker compose run --build --rm chummer-tests sh -lc \
    "cd /src && dotnet build '$DESKTOP_PROJECT' -c Release -f '$DESKTOP_FRAMEWORK' --nologo" \
    2>&1 | tee "$DESKTOP_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== desktop build extract =="
  rg -n "Build succeeded|Build FAILED|error CS|error NU|error :" "$DESKTOP_LOG_FILE" | tail -n 200 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "amend-checksums" ]]; then
  AMEND_TARGET="${AMEND_TARGET:-${RUNBOOK_ARG_FRAMEWORK:-legacy/tooling/docker/Docker/Amends}}"
  AMEND_CHECKSUM_LOG_FILE="${AMEND_CHECKSUM_LOG_FILE:-$(resolve_runbook_log_file chummer-amend-checksums)}"
  set +e
  bash scripts/validate-amend-manifests.sh "$AMEND_TARGET" 2>&1 | tee "$AMEND_CHECKSUM_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== amend checksum validation summary =="
  rg -n "Validated|ERROR:" "$AMEND_CHECKSUM_LOG_FILE" | tail -n 200 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "parity-checklist" ]]; then
  PARITY_CHECKLIST_LOG_FILE="${PARITY_CHECKLIST_LOG_FILE:-$(resolve_runbook_log_file chummer-parity-checklist)}"
  set +e
  bash scripts/generate-parity-checklist.sh 2>&1 | tee "$PARITY_CHECKLIST_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== parity checklist summary =="
  rg -n "Wrote parity checklist|Summary:" "$PARITY_CHECKLIST_LOG_FILE" | tail -n 50 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "downloads-manifest" ]]; then
  MANIFEST_LOG_FILE="${MANIFEST_LOG_FILE:-$(resolve_runbook_log_file chummer-downloads-manifest)}"
  set +e
  bash scripts/generate-releases-manifest.sh 2>&1 | tee "$MANIFEST_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== manifest preview =="
  if [[ -f legacy/tooling/docker/Docker/Downloads/releases.json ]]; then
    cat legacy/tooling/docker/Docker/Downloads/releases.json
  else
    echo "legacy/tooling/docker/Docker/Downloads/releases.json not found"
  fi
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "downloads-sync" ]]; then
  DOWNLOAD_BUNDLE_DIR="${DOWNLOAD_BUNDLE_DIR:-${RUNBOOK_ARG_FRAMEWORK:-$REPO_ROOT/dist}}"
  DOWNLOAD_DEPLOY_DIR="${DOWNLOAD_DEPLOY_DIR:-${RUNBOOK_ARG_FILTER:-$REPO_ROOT/legacy/tooling/docker/Docker/Downloads}}"
  DOWNLOADS_SYNC_DEPLOY_MODE="${DOWNLOADS_SYNC_DEPLOY_MODE:-0}"
  DOWNLOADS_SYNC_VERIFY_LINKS="${DOWNLOADS_SYNC_VERIFY_LINKS:-}"
  DOWNLOADS_SYNC_VERIFY_TARGET="${DOWNLOADS_SYNC_VERIFY_TARGET:-${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-}}"
  SYNC_LOG_FILE="${SYNC_LOG_FILE:-$(resolve_runbook_log_file chummer-downloads-sync)}"
  if [[ -z "$DOWNLOADS_SYNC_VERIFY_LINKS" ]]; then
    if [[ "$DOWNLOADS_SYNC_DEPLOY_MODE" == "1" || "$DOWNLOADS_SYNC_DEPLOY_MODE" == "true" || "$DOWNLOADS_SYNC_DEPLOY_MODE" == "TRUE" ]]; then
      DOWNLOADS_SYNC_VERIFY_LINKS=true
    else
      DOWNLOADS_SYNC_VERIFY_LINKS=false
    fi
  fi
  if [[ "$DOWNLOADS_SYNC_DEPLOY_MODE" == "1" || "$DOWNLOADS_SYNC_DEPLOY_MODE" == "true" || "$DOWNLOADS_SYNC_DEPLOY_MODE" == "TRUE" ]]; then
    if [[ -z "$DOWNLOADS_SYNC_VERIFY_TARGET" ]]; then
      echo "downloads-sync deploy mode requires DOWNLOADS_SYNC_VERIFY_TARGET or CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL." >&2
      exit 1
    fi
    export CHUMMER_PORTAL_DOWNLOADS_DEPLOY_ENABLED=true
    export CHUMMER_PORTAL_DOWNLOADS_REQUIRE_PUBLISHED_VERSION=true
    export CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL="$DOWNLOADS_SYNC_VERIFY_TARGET"
  fi
  if [[ "$DOWNLOADS_SYNC_VERIFY_LINKS" == "1" || "$DOWNLOADS_SYNC_VERIFY_LINKS" == "true" || "$DOWNLOADS_SYNC_VERIFY_LINKS" == "TRUE" ]]; then
    export CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS=true
  else
    unset CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS || true
  fi
  set +e
  bash scripts/publish-download-bundle.sh "$DOWNLOAD_BUNDLE_DIR" "$DOWNLOAD_DEPLOY_DIR" 2>&1 | tee "$SYNC_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== synced manifest =="
  if [[ -f "$DOWNLOAD_DEPLOY_DIR/releases.json" ]]; then
    cat "$DOWNLOAD_DEPLOY_DIR/releases.json"
  else
    echo "$DOWNLOAD_DEPLOY_DIR/releases.json not found"
  fi
  if [[ "$DOWNLOADS_SYNC_DEPLOY_MODE" == "1" || "$DOWNLOADS_SYNC_DEPLOY_MODE" == "true" || "$DOWNLOADS_SYNC_DEPLOY_MODE" == "TRUE" ]]; then
    echo
    echo "== deployment-mode verification summary =="
    rg -n "Verified manifest at|Verified artifact links/files|failed artifact verification" "$SYNC_LOG_FILE" | tail -n 40 || true
  fi
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "downloads-sync-s3" ]]; then
  DOWNLOAD_BUNDLE_DIR="${DOWNLOAD_BUNDLE_DIR:-${RUNBOOK_ARG_FRAMEWORK:-$REPO_ROOT/dist}}"
  DOWNLOADS_SYNC_S3_VERIFY_LINKS="${DOWNLOADS_SYNC_S3_VERIFY_LINKS:-true}"
  SYNC_S3_LOG_FILE="${SYNC_S3_LOG_FILE:-$(resolve_runbook_log_file chummer-downloads-sync-s3)}"
  if [[ "$DOWNLOADS_SYNC_S3_VERIFY_LINKS" == "1" || "$DOWNLOADS_SYNC_S3_VERIFY_LINKS" == "true" || "$DOWNLOADS_SYNC_S3_VERIFY_LINKS" == "TRUE" ]]; then
    export CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS=true
  else
    unset CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS || true
  fi
  set +e
  bash scripts/publish-download-bundle-s3.sh "$DOWNLOAD_BUNDLE_DIR" 2>&1 | tee "$SYNC_S3_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== object storage sync summary =="
  rg -n "Published|Verified manifest|Verified artifact links/files|failed artifact verification|Set CHUMMER|Expected desktop-download-bundle|aws CLI" "$SYNC_S3_LOG_FILE" | tail -n 200 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "downloads-upload-http" ]]; then
  DOWNLOAD_BUNDLE_DIR="${DOWNLOAD_BUNDLE_DIR:-${RUNBOOK_ARG_FRAMEWORK:-$REPO_ROOT/Chummer.Portal/downloads}}"
  DOWNLOADS_UPLOAD_HTTP_LOG_FILE="${DOWNLOADS_UPLOAD_HTTP_LOG_FILE:-$(resolve_runbook_log_file chummer-downloads-upload-http)}"
  set +e
  bash scripts/publish-download-bundle-http.sh "$DOWNLOAD_BUNDLE_DIR" 2>&1 | tee "$DOWNLOADS_UPLOAD_HTTP_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== http upload summary =="
  rg -n "Publishing|Upload accepted|Verified route|Verified manifest|failed with HTTP|Dry run only|Exact live publish command" "$DOWNLOADS_UPLOAD_HTTP_LOG_FILE" | tail -n 200 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "downloads-verify" ]]; then
  DOWNLOADS_VERIFY_TARGET="${DOWNLOADS_VERIFY_TARGET:-${RUNBOOK_ARG_FRAMEWORK:-${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-}}}"
  DOWNLOADS_VERIFY_LINKS="${DOWNLOADS_VERIFY_LINKS:-0}"
  VERIFY_LOG_FILE="${VERIFY_LOG_FILE:-$(resolve_runbook_log_file chummer-downloads-verify)}"
  if [[ -z "$DOWNLOADS_VERIFY_TARGET" ]]; then
    echo "Set DOWNLOADS_VERIFY_TARGET, CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL, or pass a URL/path as arg #2." >&2
    exit 1
  fi
  if [[ "$DOWNLOADS_VERIFY_LINKS" == "1" || "$DOWNLOADS_VERIFY_LINKS" == "true" || "$DOWNLOADS_VERIFY_LINKS" == "TRUE" ]]; then
    export CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS=true
  else
    unset CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS || true
  fi
  set +e
  bash scripts/verify-releases-manifest.sh "$DOWNLOADS_VERIFY_TARGET" 2>&1 | tee "$VERIFY_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== manifest verification summary =="
  rg -n "Verified manifest|Verified artifact links/files|has no downloads|failed artifact verification|not found|empty" "$VERIFY_LOG_FILE" | tail -n 200 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "downloads-smoke" ]]; then
  DOWNLOADS_SMOKE_ROOT="${DOWNLOADS_SMOKE_ROOT:-$REPO_ROOT/.tmp/downloads-smoke}"
  DOWNLOADS_SMOKE_RUN_DIR="${DOWNLOADS_SMOKE_RUN_DIR:-$DOWNLOADS_SMOKE_ROOT/run-$$}"
  DOWNLOADS_SMOKE_BUNDLE_DIR="${DOWNLOADS_SMOKE_BUNDLE_DIR:-$DOWNLOADS_SMOKE_RUN_DIR/bundle}"
  DOWNLOADS_SMOKE_DEPLOY_DIR="${DOWNLOADS_SMOKE_DEPLOY_DIR:-$DOWNLOADS_SMOKE_RUN_DIR/deploy}"
  DOWNLOADS_SMOKE_LOG_FILE="${DOWNLOADS_SMOKE_LOG_FILE:-$(resolve_runbook_log_file chummer-downloads-smoke)}"
  DOWNLOADS_SMOKE_VERSION="${DOWNLOADS_SMOKE_VERSION:-smoke-0001}"
  DOWNLOADS_SMOKE_RELEASE_PROOF_PATH="${DOWNLOADS_SMOKE_RELEASE_PROOF_PATH:-$DOWNLOADS_SMOKE_RUN_DIR/local-release-proof.json}"
  mkdir -p "$DOWNLOADS_SMOKE_BUNDLE_DIR/files" "$DOWNLOADS_SMOKE_BUNDLE_DIR/proof/windows" "$DOWNLOADS_SMOKE_BUNDLE_DIR/startup-smoke" "$DOWNLOADS_SMOKE_DEPLOY_DIR"

  artifact_path="$DOWNLOADS_SMOKE_BUNDLE_DIR/files/chummer-avalonia-linux-x64-installer.deb"
  installer_path="$DOWNLOADS_SMOKE_BUNDLE_DIR/files/chummer-avalonia-win-x64-installer.exe"
  proof_path="$DOWNLOADS_SMOKE_BUNDLE_DIR/proof/windows/chummer-avalonia-win-x64-installer.exe"
  printf 'downloads smoke installer (linux deb)\n' > "$artifact_path"
  printf 'downloads smoke installer\n' > "$installer_path"
  printf 'downloads smoke proof installer\n' > "$proof_path"
  cat > "$DOWNLOADS_SMOKE_BUNDLE_DIR/releases.json" <<JSON
{
  "version": "$DOWNLOADS_SMOKE_VERSION",
  "channel": "smoke",
  "publishedAt": "2026-03-05T00:00:00Z",
  "downloads": []
}
JSON
  cat > "$DOWNLOADS_SMOKE_RELEASE_PROOF_PATH" <<JSON
{
  "status": "passed",
  "generatedAt": "2026-04-12T00:00:00Z",
  "baseUrl": "https://chummer.run",
  "journeysPassed": [
    "install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
    "organize_community_and_close_loop"
  ],
  "proofRoutes": [
    "/downloads/install/avalonia-linux-x64-installer",
    "/home/access",
    "/home/work",
    "/account/access",
    "/account/work",
    "/account/support",
    "/contact",
    "/downloads"
  ]
}
JSON
  python3 - <<'PY' "$artifact_path" "$installer_path" "$DOWNLOADS_SMOKE_BUNDLE_DIR/startup-smoke"
import hashlib
import json
import sys
from pathlib import Path

linux_path = Path(sys.argv[1])
windows_path = Path(sys.argv[2])
output_root = Path(sys.argv[3])

def sha256_for(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

receipts = [
    (
        output_root / "startup-smoke-avalonia-linux-x64.receipt.json",
        {
            "headId": "avalonia",
            "version": "smoke-0001",
            "channelId": "smoke",
            "platform": "linux",
            "arch": "x64",
            "readyCheckpoint": "pre_ui_event_loop",
            "hostClass": "linux-host",
            "operatingSystem": "Linux",
            "recordedAtUtc": "2026-04-12T00:00:00Z",
            "artifactId": "avalonia-linux-x64-installer",
            "rid": "linux-x64",
            "status": "pass",
            "artifactFileName": linux_path.name,
            "artifactRelativePath": f"files/{linux_path.name}",
            "artifactDigest": f"sha256:{sha256_for(linux_path)}",
            "artifactSha256": sha256_for(linux_path),
        },
    ),
    (
        output_root / "startup-smoke-avalonia-win-x64.receipt.json",
        {
            "headId": "avalonia",
            "version": "smoke-0001",
            "channelId": "smoke",
            "platform": "windows",
            "arch": "x64",
            "readyCheckpoint": "pre_ui_event_loop",
            "hostClass": "windows-host",
            "operatingSystem": "Windows",
            "recordedAtUtc": "2026-04-12T00:00:00Z",
            "artifactId": "avalonia-win-x64-installer",
            "rid": "win-x64",
            "status": "pass",
            "artifactFileName": windows_path.name,
            "artifactRelativePath": f"files/{windows_path.name}",
            "artifactDigest": f"sha256:{sha256_for(windows_path)}",
            "artifactSha256": sha256_for(windows_path),
        },
    ),
]

for path, payload in receipts:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

  set +e
  {
    echo "== downloads smoke fixture =="
    echo "bundle: $DOWNLOADS_SMOKE_BUNDLE_DIR"
    echo "deploy: $DOWNLOADS_SMOKE_DEPLOY_DIR"
    RUNBOOK_MODE=downloads-sync \
      DOWNLOAD_BUNDLE_DIR="$DOWNLOADS_SMOKE_BUNDLE_DIR" \
      DOWNLOAD_DEPLOY_DIR="$DOWNLOADS_SMOKE_DEPLOY_DIR" \
      RELEASE_PROOF_PATH="$DOWNLOADS_SMOKE_RELEASE_PROOF_PATH" \
      CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH="$(resolve_ui_localization_release_gate_path)" \
      CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0 \
      DOWNLOADS_SYNC_VERIFY_LINKS=1 \
      bash "$SCRIPT_DIR/runbook.sh"
    sync_status=$?
    RUNBOOK_MODE=downloads-verify \
      DOWNLOADS_VERIFY_TARGET="$DOWNLOADS_SMOKE_DEPLOY_DIR/releases.json" \
      CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0 \
      DOWNLOADS_VERIFY_LINKS=1 \
      bash "$SCRIPT_DIR/runbook.sh"
    verify_status=$?
    if [[ -f "$DOWNLOADS_SMOKE_DEPLOY_DIR/proof/windows/$(basename "$proof_path")" ]]; then
      proof_status=0
      echo "downloads-smoke proof_status=0"
    else
      proof_status=1
      echo "downloads-smoke proof_status=1"
    fi
    echo "downloads-smoke sync_status=$sync_status verify_status=$verify_status"
    exit $(( sync_status != 0 || verify_status != 0 || proof_status != 0 ))
  } 2>&1 | tee "$DOWNLOADS_SMOKE_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== downloads smoke summary =="
  rg -n "downloads-smoke sync_status|downloads-smoke proof_status|Verified manifest|Verified artifact links/files|failed artifact verification" "$DOWNLOADS_SMOKE_LOG_FILE" | tail -n 200 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "ui-e2e" ]]; then
  UI_E2E_LOG_FILE="${UI_E2E_LOG_FILE:-$(resolve_runbook_log_file chummer-ui-e2e)}"
  export CHUMMER_UI_PLAYWRIGHT=1
  set +e
  bash scripts/e2e-ui.sh 2>&1 | tee "$UI_E2E_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== ui e2e summary =="
  rg -n "running playwright ui e2e|playwright ui e2e failed|ui E2E completed|Timed out waiting|request failed|skipping ui e2e|skipping playwright ui e2e|permission denied while trying to connect to the Docker daemon socket|operation not permitted" "$UI_E2E_LOG_FILE" | tail -n 200 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "portal-e2e" ]]; then
  PORTAL_E2E_LOG_FILE="${PORTAL_E2E_LOG_FILE:-$(resolve_runbook_log_file chummer-portal-e2e)}"
  export CHUMMER_PORTAL_PLAYWRIGHT=1
  set +e
  bash scripts/e2e-portal.sh 2>&1 | tee "$PORTAL_E2E_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== portal e2e summary =="
  rg -n "running portal playwright e2e|portal playwright e2e failed|portal e2e completed|skipping portal e2e|skipping portal playwright e2e|permission denied while trying to connect to the Docker daemon socket|operation not permitted" "$PORTAL_E2E_LOG_FILE" | tail -n 200 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "hub-e2e" ]]; then
  HUB_E2E_LOG_FILE="${HUB_E2E_LOG_FILE:-$(resolve_runbook_log_file chummer-hub-e2e)}"
  export CHUMMER_HUB_PLAYWRIGHT="${CHUMMER_HUB_PLAYWRIGHT:-1}"
  set +e
  bash scripts/e2e-hub.sh 2>&1 | tee "$HUB_E2E_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== hub e2e summary =="
  rg -n "hub e2e completed|hub playwright e2e failed|skipping hub e2e|skipping hub playwright e2e|hub playwright e2e completed" "$HUB_E2E_LOG_FILE" | tail -n 200 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "hub-live-audit" ]]; then
  HUB_LIVE_AUDIT_LOG_FILE="${HUB_LIVE_AUDIT_LOG_FILE:-$(resolve_runbook_log_file chummer-hub-live-audit)}"
  HUB_LIVE_AUDIT_BASE_URL="${HUB_LIVE_AUDIT_BASE_URL:-https://chummer.run}"
  HUB_LIVE_AUDIT_DELAY_SECONDS="${HUB_LIVE_AUDIT_DELAY_SECONDS:-0}"
  ensure_hub_cloudflare_tunnel "$HUB_LIVE_AUDIT_LOG_FILE"
  set +e
  python3 scripts/hub-live-audit.py --base-url "$HUB_LIVE_AUDIT_BASE_URL" --poll-seconds "$HUB_LIVE_AUDIT_DELAY_SECONDS" 2>&1 | tee "$HUB_LIVE_AUDIT_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== hub live audit summary =="
  tail -n 40 "$HUB_LIVE_AUDIT_LOG_FILE" || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "hub-closeout" ]]; then
  HUB_CLOSEOUT_LOG_FILE="${HUB_CLOSEOUT_LOG_FILE:-$(resolve_runbook_log_file chummer-hub-closeout)}"
  set +e
  bash scripts/ai/hub_closeout.sh 2>&1 | tee "$HUB_CLOSEOUT_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== hub closeout summary =="
  tail -n 60 "$HUB_CLOSEOUT_LOG_FILE" || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "docker-tests" ]]; then
  TEST_PROJECT="${TEST_PROJECT:-Chummer.Tests/Chummer.Tests.csproj}"
  TEST_FRAMEWORK="${TEST_FRAMEWORK:-${RUNBOOK_ARG_FRAMEWORK:-net10.0}}"
  TEST_FILTER="${TEST_FILTER:-$RUNBOOK_ARG_FILTER}"
  TEST_LOG_FILE="${TEST_LOG_FILE:-$(resolve_runbook_log_file chummer-docker-tests)}"
  DOCKER_TESTS_BUILD="${DOCKER_TESTS_BUILD:-1}"
  DOCKER_TESTS_SOFT_FAIL="${DOCKER_TESTS_SOFT_FAIL:-}"
  DOCKER_TESTS_PREFLIGHT_LOG="${DOCKER_TESTS_PREFLIGHT_LOG:-$(resolve_runbook_log_file chummer-docker-tests-preflight)}"
  framework_arg=""
  filter_arg=""
  build_arg=""
  if [[ -z "$DOCKER_TESTS_SOFT_FAIL" ]]; then
    if [[ "${CI:-}" == "true" || "${CI:-}" == "1" ]]; then
      DOCKER_TESTS_SOFT_FAIL=0
    else
      DOCKER_TESTS_SOFT_FAIL=1
    fi
  fi
  if [[ -n "$TEST_FRAMEWORK" ]]; then
    framework_arg="-f $TEST_FRAMEWORK"
  fi
  if [[ -n "$TEST_FILTER" ]]; then
    filter_arg="--filter \"$TEST_FILTER\""
  fi
  if [[ "$DOCKER_TESTS_BUILD" == "1" || "$DOCKER_TESTS_BUILD" == "true" || "$DOCKER_TESTS_BUILD" == "TRUE" ]]; then
    build_arg="--build"
  fi
  set +e
  docker ps >"$DOCKER_TESTS_PREFLIGHT_LOG" 2>&1
  preflight_status=$?
  set -e
  if [[ "$preflight_status" -ne 0 ]]; then
    if rg -qi "permission denied while trying to connect to the Docker daemon socket|permission denied while trying to connect to the docker API|operation not permitted" "$DOCKER_TESTS_PREFLIGHT_LOG"; then
      if [[ "$DOCKER_TESTS_SOFT_FAIL" == "1" || "$DOCKER_TESTS_SOFT_FAIL" == "true" || "$DOCKER_TESTS_SOFT_FAIL" == "TRUE" ]]; then
        echo "skipping docker-tests due docker daemon permissions (set DOCKER_TESTS_SOFT_FAIL=0 to enforce failure)." >&2
        cat "$DOCKER_TESTS_PREFLIGHT_LOG" >&2
        exit 0
      fi
    fi
    cat "$DOCKER_TESTS_PREFLIGHT_LOG" >&2
    exit "$preflight_status"
  fi
  set +e
  docker compose run $build_arg --rm chummer-tests \
    2>&1 | tee "$TEST_LOG_FILE"
  status=${PIPESTATUS[0]}
  set -e
  echo
  echo "== docker test failure extract =="
  rg -n "^\\s*Failed\\s|\\[xUnit.net\\]|Total tests:|Passed!|Failed!|Stack Trace|Error Message|Test Run Failed|permission denied while trying to connect to the Docker daemon socket|permission denied while trying to connect to the docker API|operation not permitted|skipping docker-tests due docker daemon permissions" "$TEST_LOG_FILE" | tail -n 200 || true
  exit "$status"
fi

if [[ "$RUNBOOK_MODE" == "push" ]]; then
  RUNBOOK_PUSH_ENABLE="${RUNBOOK_PUSH_ENABLE:-0}"
  if [[ "$RUNBOOK_PUSH_ENABLE" != "1" && "$RUNBOOK_PUSH_ENABLE" != "true" && "$RUNBOOK_PUSH_ENABLE" != "TRUE" ]]; then
    echo "push mode is disabled by default."
    echo "Set RUNBOOK_PUSH_ENABLE=1 to run an explicit push from this runbook."
    echo "Example: RUNBOOK_MODE=push RUNBOOK_PUSH_ENABLE=1 bash scripts/runbook.sh"
    exit 2
  fi

  git_cmd=(git --git-dir="$REPO_ROOT/.git" --work-tree="$REPO_ROOT")
  RUNBOOK_PUSH_REMOTE="${RUNBOOK_PUSH_REMOTE:-origin}"
  RUNBOOK_PUSH_REF="${RUNBOOK_PUSH_REF:-}"
  BRANCH_NAME="$(${git_cmd[@]} rev-parse --abbrev-ref HEAD)"
  REF_SPEC="${RUNBOOK_PUSH_REF:-$BRANCH_NAME}"

  echo "== push mode =="
  echo "branch: $BRANCH_NAME"
  echo "status: $(${git_cmd[@]} status --short --branch | head -n 1)"
  echo "remote: $RUNBOOK_PUSH_REMOTE"
  echo "refspec: $REF_SPEC"

  "${git_cmd[@]}" push "$RUNBOOK_PUSH_REMOTE" "$REF_SPEC"
  echo "push completed"
  exit "$?"
fi

if [[ "$RUNBOOK_MODE" == "hub-ship" ]]; then
  RUNBOOK_PUSH_ENABLE="${RUNBOOK_PUSH_ENABLE:-0}"
  if [[ "$RUNBOOK_PUSH_ENABLE" != "1" && "$RUNBOOK_PUSH_ENABLE" != "true" && "$RUNBOOK_PUSH_ENABLE" != "TRUE" ]]; then
    echo "hub-ship mode is disabled by default."
    echo "Set RUNBOOK_PUSH_ENABLE=1 to push and then audit live."
    exit 2
  fi

  RUNBOOK_HUB_SHIP_DELAY_SECONDS="${RUNBOOK_HUB_SHIP_DELAY_SECONDS:-15}"
  RUNBOOK_HUB_SHIP_BASE_URL="${RUNBOOK_HUB_SHIP_BASE_URL:-https://chummer.run}"
  RUNBOOK_MODE=push bash "$SCRIPT_DIR/runbook.sh"
  ensure_hub_cloudflare_tunnel "/dev/null"
  python3 scripts/hub-live-audit.py --base-url "$RUNBOOK_HUB_SHIP_BASE_URL" --poll-seconds "$RUNBOOK_HUB_SHIP_DELAY_SECONDS"
  exit 0
fi

echo "== docker ps (chummer/cloudflared) =="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | rg -i 'chummer|cloudflared' || true

echo
echo "== recent cloudflared config/events for chummer (24h) =="
docker logs --since 24h "$TUNNEL_CONTAINER" 2>&1 \
  | rg -n 'Updated to new configuration|chummer\.girschele\.com|originService=.*chummer|lookup chummer-web|Unable to reach the origin service' -i \
  | tail -n 200 || true

echo
echo "== network probe from Docker network: $DOCKER_NETWORK =="
docker run --rm \
  --network "$DOCKER_NETWORK" \
  -e U1="$UPSTREAM_PRIMARY" \
  -e U2="$UPSTREAM_UI" \
  -e U3="$UPSTREAM_LEGACY" \
  -e U4="$UPSTREAM_UI_SERVICE" \
  -e U5="$UPSTREAM_HOST_INTERNAL" \
  busybox sh -lc '
for u in "$U1" "$U2" "$U3" "$U4" "$U5"; do
  echo "--- origin: $u"
  for p in / /api/health /api/info; do
    echo "GET $p"
    wget -qSO- --timeout=3 "$u$p" -O - 2>&1 || true
    echo
  done
  echo
 done
'
