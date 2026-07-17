#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE_ROOT="${CHUMMER_RUN_SERVICES_SOURCE:-$ROOT_DIR}"
SOURCE_ROOT="$(cd "$SOURCE_ROOT" && pwd)"
EXPECTED_HEAD="${CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD:-$(git -C "$SOURCE_ROOT" rev-parse HEAD)}"
BUILD_CONTEXT="${CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT:-/docker/chummercomplete}"
COMPOSE_FILE_INPUT="${CHUMMER_PUBLIC_EDGE_COMPOSE_FILE:-$ROOT_DIR/docker-compose.public-edge.yml}"
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
PORTAL_READY_TIMEOUT_SECONDS="${CHUMMER_PUBLIC_EDGE_PORTAL_READY_TIMEOUT_SECONDS:-180}"
PUBLIC_EDGE_PORT="${CHUMMER_PUBLIC_EDGE_PORT:-8091}"
DEPLOY_LOCK_ROOT="/docker/chummercomplete/.state"
DEPLOY_LOCK_DIR="$DEPLOY_LOCK_ROOT/public-edge-mutation.lock"

if [[ "$COMPOSE_FILE_INPUT" != /* ]]; then
  COMPOSE_FILE_INPUT="$SOURCE_ROOT/$COMPOSE_FILE_INPUT"
fi
if ! COMPOSE_FILE="$(realpath -e -- "$COMPOSE_FILE_INPUT")"; then
  echo "public edge Compose file does not exist: $COMPOSE_FILE_INPUT" >&2
  exit 2
fi
CANONICAL_COMPOSE_FILE="$(realpath -e -- "$SOURCE_ROOT/docker-compose.public-edge.yml")"
if [[ "$COMPOSE_FILE" != "$CANONICAL_COMPOSE_FILE" ]]; then
  echo "public edge deploy refuses a Compose file outside the audited source root" >&2
  exit 2
fi

if [[ ! -d "$BUILD_CONTEXT" ]]; then
  echo "public edge build context does not exist: $BUILD_CONTEXT" >&2
  exit 2
fi
if [[ ! -f "$SOURCE_ROOT/Chummer.Run.Api/Dockerfile" ]]; then
  echo "portal Dockerfile is missing from audited source: $SOURCE_ROOT/Chummer.Run.Api/Dockerfile" >&2
  exit 2
fi
if [[ ! "$PORTAL_READY_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "public edge portal readiness timeout must be a positive integer" >&2
  exit 2
fi
if [[ ! "$PUBLIC_EDGE_PORT" =~ ^[1-9][0-9]{0,4}$ || "$PUBLIC_EDGE_PORT" -gt 65535 ]]; then
  echo "public edge host port must be an integer from 1 through 65535" >&2
  exit 2
fi
if [[ ! "$POSTDEPLOY_ATTEMPTS" =~ ^[1-9][0-9]*$ ]]; then
  echo "public edge postdeploy attempts must be a positive integer" >&2
  exit 2
fi
if [[ ! "$POSTDEPLOY_RETRY_DELAY_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "public edge postdeploy retry delay must be a nonnegative integer" >&2
  exit 2
fi
if [[ ! "$COMPOSE_PROJECT" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "public edge Compose project must be a safe literal identifier" >&2
  exit 2
fi
export CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT="$BUILD_CONTEXT"
export CHUMMER_RUN_SERVICES_CONTEXT_DIR="$SOURCE_ROOT"
export CHUMMER_RUN_SERVICES_SOURCE="$SOURCE_ROOT"

install -d -m 0700 -- "$DEPLOY_LOCK_ROOT"
if [[ ! -d "$DEPLOY_LOCK_ROOT" || -L "$DEPLOY_LOCK_ROOT" || ! -O "$DEPLOY_LOCK_ROOT" ]]; then
  echo "public edge deploy lock root is not a caller-owned directory" >&2
  exit 2
fi
chmod 0700 -- "$DEPLOY_LOCK_ROOT"
if ! mkdir -m 0700 -- "$DEPLOY_LOCK_DIR"; then
  echo "another public-edge mutation owns the shared deployment authority" >&2
  exit 75
fi
deploy_lock_active=1

release_deploy_lock() {
  if ((deploy_lock_active == 0)); then
    return 0
  fi
  rmdir -- "$DEPLOY_LOCK_DIR" || return 1
  deploy_lock_active=0
}

release_only_on_exit() {
  local failure_status="$?"
  trap - EXIT
  if ! release_deploy_lock; then
    echo "failed to release public edge deployment lock" >&2
    exit 70
  fi
  exit "$failure_status"
}

trap release_only_on_exit EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

compose_args=(-p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE")
if [[ -f "$ENV_FILE" ]]; then
  compose_args=(--env-file "$ENV_FILE" "${compose_args[@]}")
fi

# Run every non-mutating gate before the image build can retag the local deployment image.
# Compose interpolation is intentionally checked here so missing certificate, PostgreSQL,
# and release-shelf posture inputs cannot fail only after the build or portal quiesce.
python3 "$SOURCE_ROOT/scripts/check_public_edge_deploy_preflight.py" \
    --source-root "$SOURCE_ROOT"
docker compose "${compose_args[@]}" config --quiet

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

python3 "$SOURCE_ROOT/scripts/verify_public_edge_deploy_source.py" "${source_gate_args[@]}"

resolve_image_tag_id() {
  local resolved_ids
  if ! resolved_ids="$(docker image ls --quiet --no-trunc --filter "reference=$1")"; then
    return 1
  fi
  resolved_ids="$(printf '%s\n' "$resolved_ids" | awk 'NF && !seen[$0]++')"
  if [[ "$resolved_ids" == *$'\n'* ]]; then
    return 1
  fi
  printf '%s' "$resolved_ids"
}

if ! prior_image_tag_id="$(resolve_image_tag_id "$IMAGE_TAG")"; then
  echo "could not query prior portal image tag identity for $IMAGE_TAG" >&2
  exit 3
fi
if [[ -n "$prior_image_tag_id" && "$prior_image_tag_id" != sha256:* ]]; then
  echo "could not resolve prior portal image tag identity for $IMAGE_TAG" >&2
  exit 3
fi

restore_prior_image_tag() {
  local current_image_tag_id
  current_image_tag_id="$(resolve_image_tag_id "$IMAGE_TAG")" || return 1
  if [[ -n "$prior_image_tag_id" ]]; then
    if [[ "$current_image_tag_id" != "$prior_image_tag_id" ]]; then
      docker tag "$prior_image_tag_id" "$IMAGE_TAG" || return 1
    fi
  elif [[ -n "$current_image_tag_id" ]]; then
    docker image rm "$IMAGE_TAG" >/dev/null || return 1
  fi
}

image_tag_transaction_active=1
rollback_image_tag_on_exit() {
  local failure_status="$?"
  trap - EXIT
  if ((image_tag_transaction_active == 1)) && ! restore_prior_image_tag; then
    printf 'failed to restore prior public-edge image tag %s\n' "$prior_image_tag_id" >&2
    release_deploy_lock || true
    exit 70
  fi
  if ! release_deploy_lock; then
    printf 'failed to release public edge deployment lock\n' >&2
    exit 70
  fi
  exit "$failure_status"
}

trap rollback_image_tag_on_exit EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

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

if ! prior_portal_container_id="$(docker compose "${compose_args[@]}" ps --all -q chummer-portal)"; then
  echo "could not query prior public-edge portal container" >&2
  exit 3
fi
if [[ "$prior_portal_container_id" == *$'\n'* ]]; then
  echo "public-edge portal resolved to more than one prior container" >&2
  exit 3
fi
prior_portal_image_id=""
prior_portal_was_running=0
prior_portal_existed=0
if [[ -n "$prior_portal_container_id" ]]; then
  prior_portal_existed=1
  if ! prior_portal_image_id="$(docker container inspect --format '{{.Image}}' "$prior_portal_container_id")"; then
    echo "could not inspect prior public-edge portal image" >&2
    exit 3
  fi
  if ! prior_portal_running_state="$(docker container inspect --format '{{.State.Running}}' "$prior_portal_container_id")"; then
    echo "could not inspect prior public-edge portal runtime state" >&2
    exit 3
  fi
  if [[ "$prior_portal_running_state" == "true" ]]; then
    prior_portal_was_running=1
  elif [[ "$prior_portal_running_state" != "false" ]]; then
    echo "prior public-edge portal returned an invalid runtime state" >&2
    exit 3
  fi
fi

wait_for_restored_portal_runtime() {
  local container_id="$1"
  local deadline=$((SECONDS + PORTAL_READY_TIMEOUT_SECONDS))
  local running health
  while ((SECONDS < deadline)); do
    running="$(docker container inspect --format '{{.State.Running}}' "$container_id")" || return 1
    if [[ "$running" == "true" ]]; then
      health="$(docker container inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")" || return 1
      case "$health" in
        healthy) return 0 ;;
        none)
          timeout --kill-after=5s 30s \
            curl --fail --silent --show-error --max-time 20 \
              --output /dev/null --header 'Host: chummer.run' \
              "http://127.0.0.1:${PUBLIC_EDGE_PORT}/api/ready" \
            && return 0
          return 1
          ;;
        unhealthy) return 1 ;;
        "") return 1 ;;
      esac
    elif [[ "$running" != "false" ]]; then
      return 1
    fi
    sleep 1
  done
  return 1
}

restore_prior_portal() {
  if ((replacement_portal_may_exist == 1)); then
    if ! docker compose "${compose_args[@]}" stop chummer-portal \
      || ! docker compose "${compose_args[@]}" rm -f -s chummer-portal; then
      printf 'failed to remove replacement public-edge portal before rollback\n' >&2
      return 1
    fi
    replacement_portal_may_exist=0
  fi

  if ((prior_portal_existed == 0)); then
    return 0
  fi

  if ((prior_portal_was_running == 0)); then
    if docker container inspect "$prior_portal_container_id" >/dev/null 2>&1; then
      prior_portal_running_state="$(docker container inspect --format '{{.State.Running}}' "$prior_portal_container_id")" || return 1
      [[ "$prior_portal_running_state" == "false" ]] || return 1
      return 0
    fi
    if [[ "$prior_portal_image_id" != sha256:* ]] \
      || ! docker image inspect "$prior_portal_image_id" >/dev/null 2>&1 \
      || ! docker tag "$prior_portal_image_id" "$IMAGE_TAG" \
      || ! docker compose "${compose_args[@]}" create --no-build --force-recreate chummer-portal; then
      return 1
    fi
    prior_portal_container_id="$(docker compose "${compose_args[@]}" ps --all -q chummer-portal)" || return 1
    [[ -n "$prior_portal_container_id" && "$prior_portal_container_id" != *$'\n'* ]] || return 1
    [[ "$(docker container inspect --format '{{.Image}}' "$prior_portal_container_id")" == "$prior_portal_image_id" ]] || return 1
    [[ "$(docker container inspect --format '{{.State.Running}}' "$prior_portal_container_id")" == "false" ]] || return 1
    printf 'prior_public_edge_portal_stopped_state_restored %s\n' "$prior_portal_image_id" >&2
    return 0
  fi

  if docker container inspect "$prior_portal_container_id" >/dev/null 2>&1 \
    && docker start "$prior_portal_container_id" >/dev/null \
    && wait_for_restored_portal_runtime "$prior_portal_container_id"; then
    printf 'prior_public_edge_portal_restarted %s\n' "$prior_portal_container_id" >&2
    return 0
  fi

  if [[ "$prior_portal_image_id" == sha256:* ]] \
    && docker image inspect "$prior_portal_image_id" >/dev/null 2>&1 \
    && docker tag "$prior_portal_image_id" "$IMAGE_TAG" \
    && docker compose "${compose_args[@]}" up -d --no-build --no-deps --force-recreate \
      --wait --wait-timeout "$PORTAL_READY_TIMEOUT_SECONDS" chummer-portal; then
    printf 'prior_public_edge_portal_image_restored %s\n' "$prior_portal_image_id" >&2
    return 0
  fi

  printf 'failed to restore prior public-edge portal %s (%s)\n' \
    "$prior_portal_container_id" "$prior_portal_image_id" >&2
  return 1
}

portal_transaction_active=0
replacement_portal_may_exist=0
rollback_portal_on_exit() {
  local failure_status="$?"
  local rollback_failed=0
  trap - EXIT
  if ((portal_transaction_active == 1)); then
    restore_prior_portal || rollback_failed=1
  fi
  if ((image_tag_transaction_active == 1)); then
    restore_prior_image_tag || rollback_failed=1
  fi
  release_deploy_lock || rollback_failed=1
  if ((rollback_failed == 1)); then
    printf 'public-edge rollback did not restore the exact prior runtime and image tag\n' >&2
    exit 70
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
replacement_portal_may_exist=1
if ! docker compose "${compose_args[@]}" up -d --no-build --no-deps --force-recreate \
  --wait --wait-timeout "$PORTAL_READY_TIMEOUT_SECONDS" chummer-portal; then
  abort_portal_recreate "recreation" 1
fi

# `/api/ready` is the container healthcheck and covers data-protection custody,
# PostgreSQL install-linking authority, and canonical shelf serving. Publication
# readiness additionally proves layout-v1 activation and the release-storage free-space
# admission gate before a replacement portal can be accepted.
if ! timeout --kill-after=5s 30s \
  docker compose "${compose_args[@]}" exec -T chummer-portal \
    curl --fail --silent --show-error --max-time 20 \
      --output /dev/null --header 'Host: chummer.run' \
      http://127.0.0.1:8080/api/ready/publication; then
  abort_portal_recreate "publication readiness" 1
fi

postdeploy_command=(
  python3 "$SOURCE_ROOT/scripts/verify_public_edge_postdeploy_gate.py"
  --self-contained-direct
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

portal_transaction_active=0
replacement_portal_may_exist=0
image_tag_transaction_active=0
if ! release_deploy_lock; then
  echo "failed to release public edge deployment lock" >&2
  exit 70
fi
trap - EXIT HUP INT TERM

printf 'public_edge_portal_deployed %s\n' "$image_id"
