#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

HUB_EDGE_COMPOSE_FILE="${HUB_EDGE_COMPOSE_FILE:-docker-compose.public-edge.yml}"
HUB_EDGE_PROJECT_NAME="${CHUMMER_HUB_EDGE_PROJECT_NAME:-chummer6-hub}"
HUB_LOCAL_BASE_URL="${HUB_LOCAL_BASE_URL:-http://127.0.0.1:${CHUMMER_PUBLIC_EDGE_PORT:-8091}}"
HUB_LIVE_BASE_URL="${HUB_LIVE_BASE_URL:-https://chummer.run}"
HUB_PUBLIC_HOST="${HUB_PUBLIC_HOST:-chummer.run}"
HUB_CLOSEOUT_BUILD="${HUB_CLOSEOUT_BUILD:-1}"
HUB_CLOSEOUT_BROWSER="${HUB_CLOSEOUT_BROWSER:-1}"
HUB_CLOSEOUT_LIVE_AUDIT="${HUB_CLOSEOUT_LIVE_AUDIT:-1}"
HUB_CLOSEOUT_INCLUDE_BLAZOR="${HUB_CLOSEOUT_INCLUDE_BLAZOR:-0}"
HUB_ENV_FILE="${CHUMMER_HUB_ENV_FILE:-}"
PUBLIC_EDGE_DEPLOY_SOURCE_GATE="${CHUMMER_PUBLIC_EDGE_DEPLOY_SOURCE_GATE:-1}"
PUBLIC_EDGE_EXPECTED_HEAD="${CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD:-}"
PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE="${CHUMMER_PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE:-1}"
AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG="${CHUMMER_AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG:-$ROOT_DIR/.state/auth_signin_automation_paused.flag}"
WORKSPACE_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
BUILD_PROVENANCE_PYTHON="${CHUMMER_BUILD_PROVENANCE_PYTHON:-python3}"
BUILD_PROVENANCE_GENERATOR="${CHUMMER_RUN_SERVICES_BUILD_PROVENANCE_GENERATOR:-$WORKSPACE_ROOT/scripts/release/materialize_build_provenance.py}"
BUILD_PROVENANCE_INVOCATION_DIR="${CHUMMER_RUN_SERVICES_BUILD_PROVENANCE_INVOCATION_DIR:-$WORKSPACE_ROOT/.codex-studio/published/build-provenance/invocations}"
BUILD_PROVENANCE_SBOM_DIR="${CHUMMER_RUN_SERVICES_BUILD_PROVENANCE_SBOM_DIR:-$WORKSPACE_ROOT/.codex-studio/published/sbom}"
BUILD_PROVENANCE_STATE_ROOT="${CHUMMER_RUN_SERVICES_BUILD_PROVENANCE_STATE_ROOT:-$WORKSPACE_ROOT/.tmp/ai/run-services-build-provenance}"
BUILD_PROVENANCE_PRESENTATION_ROOT="${CHUMMER_RUN_SERVICES_SOURCE_PRESENTATION_ROOT:-$WORKSPACE_ROOT/chummer-presentation}"
BUILD_PROVENANCE_CORE_ROOT="${CHUMMER_RUN_SERVICES_SOURCE_CORE_ROOT:-$WORKSPACE_ROOT/chummer-core-engine}"
BUILD_PROVENANCE_UI_KIT_ROOT="${CHUMMER_RUN_SERVICES_SOURCE_UI_KIT_ROOT:-$WORKSPACE_ROOT/chummer-ui-kit}"
BUILD_PROVENANCE_REGISTRY_ROOT="${CHUMMER_RUN_SERVICES_SOURCE_REGISTRY_ROOT:-$WORKSPACE_ROOT/chummer-hub-registry}"
BUILD_PROVENANCE_MEDIA_ROOT_DEFAULT="$WORKSPACE_ROOT/chummer-media-factory"
if [[ ! -d "$BUILD_PROVENANCE_MEDIA_ROOT_DEFAULT" && -d "$WORKSPACE_ROOT/fleet/repos/chummer-media-factory" ]]; then
  BUILD_PROVENANCE_MEDIA_ROOT_DEFAULT="$WORKSPACE_ROOT/fleet/repos/chummer-media-factory"
fi
BUILD_PROVENANCE_MEDIA_ROOT="${CHUMMER_RUN_SERVICES_SOURCE_MEDIA_ROOT:-$BUILD_PROVENANCE_MEDIA_ROOT_DEFAULT}"
BUILD_PROVENANCE_LEGACY_ROOT_DEFAULT="$WORKSPACE_ROOT/chummer5a"
if [[ ! -d "$BUILD_PROVENANCE_LEGACY_ROOT_DEFAULT" && -d "$(dirname "$WORKSPACE_ROOT")/chummer5a" ]]; then
  BUILD_PROVENANCE_LEGACY_ROOT_DEFAULT="$(dirname "$WORKSPACE_ROOT")/chummer5a"
fi
BUILD_PROVENANCE_LEGACY_ROOT="${CHUMMER_RUN_SERVICES_SOURCE_LEGACY_ROOT:-$BUILD_PROVENANCE_LEGACY_ROOT_DEFAULT}"

begin_oci_build_provenance() {
  local invocation_id="$1"
  local target_id="$2"
  local project_path="$3"
  local artifact_id="$4"
  local image_name="$5"
  local state_path="$6"
  local output_path="$7"
  local docker_binary="$8"
  local dockerfile_path="$9"

  "$BUILD_PROVENANCE_PYTHON" "$BUILD_PROVENANCE_GENERATOR" begin \
    --state "$state_path" \
    --output "$output_path" \
    --builder-id "chummer.run-services/scripts/ai/hub_closeout.sh" \
    --build-type "chummer6.run-services.public-edge-oci" \
    --invocation-id "$invocation_id" \
    --source-repository "chummer.run-services" \
    --source-repo-root "$ROOT_DIR" \
    --source-material "chummer-presentation=$BUILD_PROVENANCE_PRESENTATION_ROOT" \
    --source-material "chummer-core-engine=$BUILD_PROVENANCE_CORE_ROOT" \
    --source-material "chummer-ui-kit=$BUILD_PROVENANCE_UI_KIT_ROOT" \
    --source-material "chummer-hub-registry=$BUILD_PROVENANCE_REGISTRY_ROOT" \
    --source-material "chummer-media-factory=$BUILD_PROVENANCE_MEDIA_ROOT" \
    --source-material "chummer5a=$BUILD_PROVENANCE_LEGACY_ROOT" \
    --build-root "$ROOT_DIR" \
    --target-id "$target_id" \
    --project-path "$project_path" \
    --artifact-id "$artifact_id" \
    --artifact-kind "oci_image" \
    --artifact-name "$image_name" \
    --artifact-image "$image_name" \
    --docker-binary "$docker_binary" \
    --sbom-path "$BUILD_PROVENANCE_SBOM_DIR/$target_id.cdx.json" \
    --build-input "compose_file=$HUB_EDGE_COMPOSE_PATH" \
    --build-input "dockerfile=$dockerfile_path"
}

finalize_oci_build_provenance() {
  local invocation_id="$1"
  local state_path="$2"
  local output_path="$3"

  "$BUILD_PROVENANCE_PYTHON" "$BUILD_PROVENANCE_GENERATOR" finalize \
    --state "$state_path" \
    --output "$output_path" \
    --builder-id "chummer.run-services/scripts/ai/hub_closeout.sh" \
    --build-type "chummer6.run-services.public-edge-oci" \
    --invocation-id "$invocation_id"
}

if [[ -z "$HUB_ENV_FILE" ]]; then
  if [[ -f "$ROOT_DIR/.env" ]]; then
    HUB_ENV_FILE="$ROOT_DIR/.env"
  elif [[ -f "/docker/chummercomplete/chummer.run-services/.env" ]]; then
    HUB_ENV_FILE="/docker/chummercomplete/chummer.run-services/.env"
  fi
fi

if [[ -n "$HUB_ENV_FILE" ]]; then
  # Preserve auth-critical values from the selected env file so compose does not
  # inherit empty shell variables and silently disable sign-in on rebuild.
  while IFS='=' read -r key value; do
    case "$key" in
      IDENTITY_ADMIN_KEY|GOOGLE_OIDC_CLIENT_ID|GOOGLE_OIDC_CLIENT_SECRET|GOOGLE_OIDC_REDIRECT_URI)
        export "$key=$value"
        ;;
    esac
  done < <(grep -E '^(IDENTITY_ADMIN_KEY|GOOGLE_OIDC_CLIENT_ID|GOOGLE_OIDC_CLIENT_SECRET|GOOGLE_OIDC_REDIRECT_URI)=' "$HUB_ENV_FILE" || true)
fi

if [[ "$HUB_EDGE_COMPOSE_FILE" == /* ]]; then
  HUB_EDGE_COMPOSE_PATH="$HUB_EDGE_COMPOSE_FILE"
else
  HUB_EDGE_COMPOSE_PATH="$ROOT_DIR/$HUB_EDGE_COMPOSE_FILE"
fi

compose_args=(-p "$HUB_EDGE_PROJECT_NAME" -f "$HUB_EDGE_COMPOSE_FILE")
if [[ -n "$HUB_ENV_FILE" ]]; then
  compose_args=(--env-file "$HUB_ENV_FILE" "${compose_args[@]}")
fi

echo "== hub closeout =="
echo "local base: $HUB_LOCAL_BASE_URL"
echo "live base: $HUB_LIVE_BASE_URL"
echo "compose project: $HUB_EDGE_PROJECT_NAME"
if [[ -n "$HUB_ENV_FILE" ]]; then
  echo "compose env file: $HUB_ENV_FILE"
else
  echo "compose env file: <none>"
fi
if [[ "$HUB_CLOSEOUT_INCLUDE_BLAZOR" == "1" || "$HUB_CLOSEOUT_INCLUDE_BLAZOR" == "true" || "$HUB_CLOSEOUT_INCLUDE_BLAZOR" == "TRUE" ]]; then
  echo "include blazor lane: yes"
else
  echo "include blazor lane: no"
fi

if [[ "$HUB_CLOSEOUT_BUILD" == "1" || "$HUB_CLOSEOUT_BUILD" == "true" || "$HUB_CLOSEOUT_BUILD" == "TRUE" ]]; then
  echo
  echo "== rebuild local public edge =="
  if [[ "$PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE" == "0" || "$PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE" == "false" || "$PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE" == "FALSE" ]]; then
    echo "Public-edge deploy preflight is mandatory and cannot be disabled." >&2
    exit 2
  fi
  python3 scripts/check_public_edge_deploy_preflight.py

  if [[ "$PUBLIC_EDGE_DEPLOY_SOURCE_GATE" != "0" && "$PUBLIC_EDGE_DEPLOY_SOURCE_GATE" != "false" && "$PUBLIC_EDGE_DEPLOY_SOURCE_GATE" != "FALSE" ]]; then
    gate_args=(--repo-root "$ROOT_DIR")
    if [[ -n "$PUBLIC_EDGE_EXPECTED_HEAD" ]]; then
      gate_args+=(--expected-head "$PUBLIC_EDGE_EXPECTED_HEAD")
    fi
    python3 scripts/verify_public_edge_deploy_source.py "${gate_args[@]}"
  fi
  if [[ ! -f "$BUILD_PROVENANCE_GENERATOR" ]]; then
    echo "Run-services build provenance generator is unavailable: $BUILD_PROVENANCE_GENERATOR" >&2
    exit 1
  fi
  if [[ ! -f "$HUB_EDGE_COMPOSE_PATH" ]]; then
    echo "Public-edge compose build input is unavailable: $HUB_EDGE_COMPOSE_PATH" >&2
    exit 1
  fi
  BUILD_PROVENANCE_DOCKER_BINARY="${CHUMMER_RUN_SERVICES_BUILD_PROVENANCE_DOCKER_BINARY:-$(command -v docker || true)}"
  if [[ "$BUILD_PROVENANCE_DOCKER_BINARY" != /* || ! -x "$BUILD_PROVENANCE_DOCKER_BINARY" ]]; then
    echo "Build provenance requires an absolute existing Docker executable." >&2
    exit 1
  fi

  echo
  echo "== prepare public-edge OCI build provenance =="
  dotnet restore Chummer.Run.Api/Chummer.Run.Api.csproj --nologo
  dotnet restore Chummer.Run.Identity/Chummer.Run.Identity.csproj --nologo
  provenance_run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  provenance_state_dir="$BUILD_PROVENANCE_STATE_ROOT/$provenance_run_id"
  mkdir -p "$BUILD_PROVENANCE_INVOCATION_DIR" "$BUILD_PROVENANCE_SBOM_DIR" "$provenance_state_dir"
  identity_provenance_invocation_id="run-services-identity-$provenance_run_id"
  api_provenance_invocation_id="run-services-api-$provenance_run_id"
  identity_provenance_state="$provenance_state_dir/$identity_provenance_invocation_id.state.json"
  api_provenance_state="$provenance_state_dir/$api_provenance_invocation_id.state.json"
  identity_provenance_receipt="$BUILD_PROVENANCE_INVOCATION_DIR/$identity_provenance_invocation_id.json"
  api_provenance_receipt="$BUILD_PROVENANCE_INVOCATION_DIR/$api_provenance_invocation_id.json"

  begin_oci_build_provenance "$identity_provenance_invocation_id" "run-services-identity" "Chummer.Run.Identity/Chummer.Run.Identity.csproj" "run-services-identity" "chummer-run-identity:local" "$identity_provenance_state" "$identity_provenance_receipt" "$BUILD_PROVENANCE_DOCKER_BINARY" "$ROOT_DIR/Chummer.Run.Identity/Dockerfile"
  begin_oci_build_provenance "$api_provenance_invocation_id" "run-services-api" "Chummer.Run.Api/Chummer.Run.Api.csproj" "run-services-api" "chummer-run-api:local" "$api_provenance_state" "$api_provenance_receipt" "$BUILD_PROVENANCE_DOCKER_BINARY" "$ROOT_DIR/Chummer.Run.Api/Dockerfile"
  public_edge_services=(chummer-run-identity chummer-portal)
  if [[ "$HUB_CLOSEOUT_INCLUDE_BLAZOR" == "1" || "$HUB_CLOSEOUT_INCLUDE_BLAZOR" == "true" || "$HUB_CLOSEOUT_INCLUDE_BLAZOR" == "TRUE" ]]; then
    public_edge_services+=(chummer-public-blazor)
  fi
  "$BUILD_PROVENANCE_DOCKER_BINARY" compose "${compose_args[@]}" up -d --build --remove-orphans "${public_edge_services[@]}"
  finalize_oci_build_provenance "$identity_provenance_invocation_id" "$identity_provenance_state" "$identity_provenance_receipt"
  finalize_oci_build_provenance "$api_provenance_invocation_id" "$api_provenance_state" "$api_provenance_receipt"
  echo "OCI build provenance receipts: $identity_provenance_receipt $api_provenance_receipt"
fi

echo
echo "== build + verification =="
dotnet build Chummer.Run.sln --nologo
bash scripts/ai/run_services_smoke.sh

if [[ "$HUB_CLOSEOUT_BROWSER" == "1" || "$HUB_CLOSEOUT_BROWSER" == "true" || "$HUB_CLOSEOUT_BROWSER" == "TRUE" ]]; then
  CHUMMER_HUB_PLAYWRIGHT=1 CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/ai/run_services_verification.sh
else
  bash scripts/ai/run_services_verification.sh
fi

echo
echo "== local route audit =="
hub_live_audit_args=(
  --base-url "$HUB_LOCAL_BASE_URL"
  --public-host "$HUB_PUBLIC_HOST"
  --forwarded-proto https
  --verify-http-redirects
)
if [[ -f "$AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG" ]]; then
  echo "skipping signed-in hub audit: auth/sign-in automation is paused at $AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG"
else
  hub_live_audit_args+=(--verify-signed-in-work)
fi
python3 scripts/hub-live-audit.py "${hub_live_audit_args[@]}"

if [[ "$HUB_CLOSEOUT_LIVE_AUDIT" == "1" || "$HUB_CLOSEOUT_LIVE_AUDIT" == "true" || "$HUB_CLOSEOUT_LIVE_AUDIT" == "TRUE" ]]; then
  echo
  echo "== live route audit =="
  python3 scripts/hub-live-audit.py --base-url "$HUB_LIVE_BASE_URL"
  python3 scripts/verify_live_public_windows_installer.py --base-url "$HUB_LIVE_BASE_URL"
fi

echo
echo "hub closeout passed"
