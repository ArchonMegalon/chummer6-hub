#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE_ROOT="${CHUMMER_RUN_SERVICES_SOURCE:-$ROOT_DIR}"
SOURCE_ROOT="$(cd "$SOURCE_ROOT" && pwd)"
EXPECTED_HEAD="${CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD:-$(git -C "$SOURCE_ROOT" rev-parse HEAD)}"
BUILD_CONTEXT="${CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT:-/docker/chummercomplete}"
COMPOSE_FILE="${CHUMMER_PUBLIC_EDGE_COMPOSE_FILE:-$ROOT_DIR/docker-compose.public-edge.yml}"
COMPOSE_PROJECT="${CHUMMER_PUBLIC_EDGE_PROJECT_NAME:-chummer6-hub}"
ENV_FILE="${CHUMMER_PUBLIC_EDGE_ENV_FILE:-/docker/chummercomplete/chummer.run-services/.env}"
IMAGE_TAG="${CHUMMER_PUBLIC_EDGE_PORTAL_IMAGE_TAG:-chummer-run-api:local}"
BASE_URL="${CHUMMER_PUBLIC_EDGE_BASE_URL:-https://chummer.run}"
RELEASE_CHANNEL="${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL:-nightly}"
FLEET_MEDIA_CONTRACTS="${CHUMMER_FLEET_MEDIA_CONTRACTS:-/docker/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts}"
DESIGN_PRODUCT_ROOT="${CHUMMER_DESIGN_PRODUCT_ROOT:-/docker/chummercomplete/chummer-design}"
BUILD_CONCURRENCY="${CHUMMER_BUILD_CONCURRENCY:-1}"
POSTDEPLOY_OUTPUT="${CHUMMER_PUBLIC_EDGE_POSTDEPLOY_OUTPUT:-$SOURCE_ROOT/.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json}"
PLAYWRIGHT_ARTIFACT_DIR="${CHUMMER_PUBLIC_EDGE_PLAYWRIGHT_ARTIFACT_DIR:-$SOURCE_ROOT/.codex-studio/published/public-edge-browser-proofs}"
PROGRESS="${CHUMMER_PUBLIC_EDGE_BUILD_PROGRESS:-auto}"
POSTDEPLOY_ATTEMPTS="${CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS:-3}"
POSTDEPLOY_RETRY_DELAY_SECONDS="${CHUMMER_PUBLIC_EDGE_POSTDEPLOY_RETRY_DELAY_SECONDS:-10}"

if [[ ! -d "$BUILD_CONTEXT" ]]; then
  echo "public edge build context does not exist: $BUILD_CONTEXT" >&2
  exit 2
fi
if [[ ! -f "$SOURCE_ROOT/Chummer.Run.Api/Dockerfile" ]]; then
  echo "portal Dockerfile is missing from audited source: $SOURCE_ROOT/Chummer.Run.Api/Dockerfile" >&2
  exit 2
fi

source_gate_args=(
  --repo-root "$SOURCE_ROOT"
  --expected-head "$EXPECTED_HEAD"
  --compose-file "$COMPOSE_FILE"
  --compose-service chummer-portal
)

case "${CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM:-auto}" in
  1|true|TRUE|yes|YES|on|ON)
    source_gate_args+=(--require-upstream)
    ;;
  auto)
    if git -C "$SOURCE_ROOT" rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
      source_gate_args+=(--require-upstream)
    fi
    ;;
esac

if [[ "${CHUMMER_PUBLIC_EDGE_IGNORE_GENERATED_PROOF_DRIFT:-0}" =~ ^(1|true|TRUE|yes|YES|on|ON)$ ]]; then
  source_gate_args+=(--ignore-generated-proof-drift)
fi

CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT="$BUILD_CONTEXT" \
CHUMMER_RUN_SERVICES_CONTEXT_DIR="$SOURCE_ROOT" \
CHUMMER_RUN_SERVICES_SOURCE="$SOURCE_ROOT" \
  python3 "$SOURCE_ROOT/scripts/verify_public_edge_deploy_source.py" "${source_gate_args[@]}"

docker buildx build \
  --load \
  --progress="$PROGRESS" \
  -t "$IMAGE_TAG" \
  -f "$SOURCE_ROOT/Chummer.Run.Api/Dockerfile" \
  --build-context "run-services-source=$SOURCE_ROOT" \
  --build-context "fleet-media-factory-contracts=$FLEET_MEDIA_CONTRACTS" \
  --build-context "design-product=$DESIGN_PRODUCT_ROOT" \
  --build-arg "CHUMMER_BUILD_CONCURRENCY=$BUILD_CONCURRENCY" \
  "$BUILD_CONTEXT"

image_id="$(docker image inspect "$IMAGE_TAG" --format '{{.Id}}')"
if [[ -z "$image_id" || "$image_id" != sha256:* ]]; then
  echo "could not resolve built portal image id for $IMAGE_TAG" >&2
  exit 3
fi

compose_args=(-p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE")
if [[ -f "$ENV_FILE" ]]; then
  compose_args=(--env-file "$ENV_FILE" "${compose_args[@]}")
fi

prior_portal_container_id="$(docker compose "${compose_args[@]}" ps -q chummer-portal 2>/dev/null || true)"
prior_portal_image_id=""
prior_portal_was_running=0
if [[ -n "$prior_portal_container_id" ]]; then
  prior_portal_image_id="$(docker container inspect --format '{{.Image}}' "$prior_portal_container_id" 2>/dev/null || true)"
  if [[ "$(docker container inspect --format '{{.State.Running}}' "$prior_portal_container_id" 2>/dev/null || true)" == "true" ]]; then
    prior_portal_was_running=1
  fi
fi

restore_prior_portal() {
  if ((prior_portal_was_running == 0)); then
    return 0
  fi

  if docker container inspect "$prior_portal_container_id" >/dev/null 2>&1 \
    && docker start "$prior_portal_container_id" >/dev/null; then
    printf 'prior_public_edge_portal_restarted %s\n' "$prior_portal_container_id" >&2
    return 0
  fi

  if [[ "$prior_portal_image_id" == sha256:* ]] \
    && docker image inspect "$prior_portal_image_id" >/dev/null 2>&1 \
    && docker tag "$prior_portal_image_id" "$IMAGE_TAG" \
    && docker compose "${compose_args[@]}" up -d --no-build --no-deps --force-recreate chummer-portal; then
    printf 'prior_public_edge_portal_image_restored %s\n' "$prior_portal_image_id" >&2
    return 0
  fi

  printf 'failed to restore prior public-edge portal %s (%s)\n' \
    "$prior_portal_container_id" "$prior_portal_image_id" >&2
  return 1
}

portal_transaction_active=0
rollback_portal_on_exit() {
  local failure_status="$?"
  trap - EXIT
  if ((portal_transaction_active == 1)); then
    restore_prior_portal || true
  fi
  exit "$failure_status"
}

abort_portal_recreate() {
  local failure_label="$1"
  local failure_status="$2"
  printf 'public-edge portal %s failed; attempting prior portal restore\n' "$failure_label" >&2
  exit "$failure_status"
}

trap rollback_portal_on_exit EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

portal_transaction_active=1
if ! docker compose "${compose_args[@]}" stop chummer-portal; then
  abort_portal_recreate "quiesce" 1
fi
if ! docker compose "${compose_args[@]}" run --rm --no-deps chummer-portal-volume-init; then
  abort_portal_recreate "volume initialization" 1
fi
if ! docker compose "${compose_args[@]}" up -d --no-build --no-deps --force-recreate chummer-portal; then
  abort_portal_recreate "recreation" 1
fi
portal_transaction_active=0
trap - EXIT HUP INT TERM

postdeploy_command=(
  python3 "$SOURCE_ROOT/scripts/verify_public_edge_postdeploy_gate.py"
  --base-url "$BASE_URL"
  --expected-release-channel "$RELEASE_CHANNEL"
  --expected-portal-image-id "$image_id"
  --require-downloads-status-playwright
  --require-mobile-pwa-viewport-playwright
  --require-frontdoor-navigation-playwright
  --playwright-artifact-dir "$PLAYWRIGHT_ARTIFACT_DIR"
  --output "$POSTDEPLOY_OUTPUT"
)

for ((attempt = 1; attempt <= POSTDEPLOY_ATTEMPTS; attempt++)); do
  if "${postdeploy_command[@]}"; then
    break
  fi
  if ((attempt == POSTDEPLOY_ATTEMPTS)); then
    exit 1
  fi
  sleep "$POSTDEPLOY_RETRY_DELAY_SECONDS"
done

printf 'public_edge_portal_deployed %s\n' "$image_id"
