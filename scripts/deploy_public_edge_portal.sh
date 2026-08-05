#!/usr/bin/bash -p
set +x
set -euo pipefail

# Required outer boundary (with the explicit CHUMMER authority/runtime inputs
# inserted before the executable):
# /usr/bin/env -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
#   CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1 ... \
#   /usr/bin/bash --noprofile --norc -p scripts/deploy_public_edge_portal.sh
if [[ "${CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH-}" != "1" ]]; then
  printf '%s\n' \
    'public edge deploy requires /usr/bin/env -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1 ... /usr/bin/bash --noprofile --norc -p' >&2
  exit 2
fi

DEPLOY_OPERATION="${1:-deploy}"
if (($# > 1)); then
  echo "usage: deploy_public_edge_portal.sh [deploy|recover|recover-adopt-verified-prior-runtime-baseline|initial-release-shelf-cutover|initial-release-shelf-cutover-recover|initial-release-shelf-public-download-cutover|initial-release-shelf-public-download-cutover-recover|initial-release-shelf-public-download-cutover-retire|release-upload-ticket-epoch-rotate|release-upload-ticket-epoch-rotate-resume]" >&2
  exit 2
fi
case "$DEPLOY_OPERATION" in
  deploy|recover|recover-adopt-verified-prior-runtime-baseline|release-upload-ticket-epoch-rotate|release-upload-ticket-epoch-rotate-resume|initial-release-shelf-cutover|initial-release-shelf-cutover-recover|initial-release-shelf-public-download-cutover|initial-release-shelf-public-download-cutover-recover|initial-release-shelf-public-download-cutover-retire) ;;
  *) echo "usage: deploy_public_edge_portal.sh [deploy|recover|recover-adopt-verified-prior-runtime-baseline|initial-release-shelf-cutover|initial-release-shelf-cutover-recover|initial-release-shelf-public-download-cutover|initial-release-shelf-public-download-cutover-recover|initial-release-shelf-public-download-cutover-retire|release-upload-ticket-epoch-rotate|release-upload-ticket-epoch-rotate-resume]" >&2; exit 2 ;;
esac
INITIAL_RELEASE_SHELF_CUTOVER=0
INITIAL_RELEASE_SHELF_CUTOVER_RECOVERY=0
PUBLIC_DOWNLOAD_ONLY_OPERATION=0
RELEASE_UPLOAD_TICKET_EPOCH_ROTATION=0
RELEASE_UPLOAD_TICKET_EPOCH_ROTATION_RESUME=0
RECOVERY_BASELINE_ADOPTION=0
if [[ "$DEPLOY_OPERATION" == initial-release-shelf-cutover ]]; then
  INITIAL_RELEASE_SHELF_CUTOVER=1
elif [[ "$DEPLOY_OPERATION" == initial-release-shelf-cutover-recover ]]; then
  INITIAL_RELEASE_SHELF_CUTOVER_RECOVERY=1
elif [[ "$DEPLOY_OPERATION" == release-upload-ticket-epoch-rotate ]]; then
  RELEASE_UPLOAD_TICKET_EPOCH_ROTATION=1
elif [[ "$DEPLOY_OPERATION" == release-upload-ticket-epoch-rotate-resume ]]; then
  RELEASE_UPLOAD_TICKET_EPOCH_ROTATION_RESUME=1
elif [[ "$DEPLOY_OPERATION" == recover-adopt-verified-prior-runtime-baseline ]]; then
  RECOVERY_BASELINE_ADOPTION=1
elif [[ "$DEPLOY_OPERATION" == initial-release-shelf-public-download-cutover \
  || "$DEPLOY_OPERATION" == initial-release-shelf-public-download-cutover-recover \
  || "$DEPLOY_OPERATION" == initial-release-shelf-public-download-cutover-retire ]]; then
  PUBLIC_DOWNLOAD_ONLY_OPERATION=1
fi

readonly TRUSTED_GIT="/usr/bin/git"
readonly TRUSTED_PYTHON="/usr/bin/python3"
readonly TRUSTED_DOCKER="/usr/bin/docker"
readonly TRUSTED_TIMEOUT="/usr/bin/timeout"
readonly TRUSTED_REALPATH="/usr/bin/realpath"
readonly TRUSTED_INSTALL="/usr/bin/install"
readonly TRUSTED_CHMOD="/usr/bin/chmod"
readonly TRUSTED_MKDIR="/usr/bin/mkdir"
readonly TRUSTED_RMDIR="/usr/bin/rmdir"
readonly TRUSTED_AWK="/usr/bin/awk"
readonly TRUSTED_SLEEP="/usr/bin/sleep"
readonly TRUSTED_ENV="/usr/bin/env"
readonly TRUSTED_DIRNAME="/usr/bin/dirname"
readonly TRUSTED_STAT="/usr/bin/stat"
readonly TRUSTED_SHA256SUM="/usr/bin/sha256sum"
readonly TRUSTED_MKTEMP="/usr/bin/mktemp"
readonly TRUSTED_RM="/usr/bin/rm"
readonly TRUSTED_FLOCK="/usr/bin/flock"

for trusted_tool in \
  "$TRUSTED_GIT" "$TRUSTED_PYTHON" "$TRUSTED_DOCKER" \
  "$TRUSTED_TIMEOUT" "$TRUSTED_REALPATH" "$TRUSTED_INSTALL" "$TRUSTED_CHMOD" \
  "$TRUSTED_MKDIR" "$TRUSTED_RMDIR" "$TRUSTED_AWK" "$TRUSTED_SLEEP" \
  "$TRUSTED_ENV" "$TRUSTED_DIRNAME" "$TRUSTED_STAT" "$TRUSTED_SHA256SUM" \
  "$TRUSTED_MKTEMP" "$TRUSTED_RM" "$TRUSTED_FLOCK"; do
  if [[ ! -x "$trusted_tool" ]]; then
    printf 'trusted public-edge tool is unavailable: %s\n' "$trusted_tool" >&2
    exit 2
  fi
done

# A caller may select source and authority inputs, but it may not steer language
# startup hooks, Docker transports/configuration, BuildKit, Buildx, or Compose.
ambient_routing_names=()
while IFS='=' read -r ambient_name _ambient_value; do
  case "$ambient_name" in
    BASH_ENV|BASHOPTS|BASH_XTRACEFD|ENV|PS4|SHELLOPTS|CDPATH|GLOBIGNORE|LD_PRELOAD|LD_LIBRARY_PATH|PYTHONHOME|PYTHONPATH|PYTHONSTARTUP|PYTHONINSPECT|PYTHONBREAKPOINT|PYTHONWARNINGS|PYTHONSAFEPATH|DOCKER_*|BUILDKIT_HOST|BUILDX_*|COMPOSE_*)
      ambient_routing_names+=("$ambient_name")
      ;;
  esac
done < <("$TRUSTED_ENV")
if ((${#ambient_routing_names[@]} > 0)); then
  for ambient_name in "${ambient_routing_names[@]}"; do
    unset "$ambient_name" 2>/dev/null || true
  done
  printf 'public edge deploy rejects ambient execution routing: %s\n' \
    "${ambient_routing_names[*]}" >&2
  exit 2
fi

SCRIPT_PATH="$("$TRUSTED_REALPATH" -e -- "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$("$TRUSTED_DIRNAME" -- "$SCRIPT_PATH")"
ROOT_DIR="$("$TRUSTED_REALPATH" -e -- "$SCRIPT_DIR/..")"

SOURCE_ROOT_INPUT="${CHUMMER_RUN_SERVICES_SOURCE:-$ROOT_DIR}"
if ! SOURCE_ROOT="$("$TRUSTED_REALPATH" -e -- "$SOURCE_ROOT_INPUT")"; then
  echo "selected public edge source does not exist: $SOURCE_ROOT_INPUT" >&2
  exit 2
fi
EXPECTED_HEAD="${CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD-}"
EXPECTED_UPSTREAM_REF="${CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF-}"
EXPECTED_AUTHORITY_VERIFIER_SHA256="${CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256-}"
if [[ ! "$EXPECTED_HEAD" =~ ^[0-9A-Fa-f]{40}$ ]]; then
  echo "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD must be externally supplied as a full 40-hex commit" >&2
  exit 2
fi
if [[ ! "$EXPECTED_UPSTREAM_REF" =~ ^refs/remotes/[A-Za-z0-9][A-Za-z0-9._/-]*[A-Za-z0-9]$ ]] \
  || [[ "$EXPECTED_UPSTREAM_REF" == *..* || "$EXPECTED_UPSTREAM_REF" == *//* \
    || "$EXPECTED_UPSTREAM_REF" == *@\{* || "$EXPECTED_UPSTREAM_REF" == *.lock ]]; then
  echo "CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF must be a full refs/remotes/... authority" >&2
  exit 2
fi
if [[ ! "$EXPECTED_AUTHORITY_VERIFIER_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256 must be an independently supplied full SHA-256" >&2
  exit 2
fi
case "${CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM:-1}" in
  1|true|TRUE|yes|YES|on|ON) ;;
  *)
    echo "public edge deploy upstream authority is mandatory and cannot be disabled" >&2
    exit 2
    ;;
esac

trusted_authority_args=(
  --repo-root "$SOURCE_ROOT"
  --expected-head "$EXPECTED_HEAD"
  --expected-upstream-ref "$EXPECTED_UPSTREAM_REF"
)
if [[ "${CHUMMER_PUBLIC_EDGE_IGNORE_GENERATED_PROOF_DRIFT:-0}" =~ ^(1|true|TRUE|yes|YES|on|ON)$ ]]; then
  trusted_authority_args+=(--ignore-generated-proof-drift)
fi
TRUSTED_AUTHORITY_VERIFIER="$ROOT_DIR/scripts/verify_public_edge_deploy_authority.py"
if [[ ! -f "$TRUSTED_AUTHORITY_VERIFIER" || -L "$TRUSTED_AUTHORITY_VERIFIER" ]]; then
  echo "wrapper-owned public edge authority verifier is missing or symlinked" >&2
  exit 2
fi
actual_authority_verifier_sha256="$(
  "$TRUSTED_SHA256SUM" -- "$TRUSTED_AUTHORITY_VERIFIER"
)"
actual_authority_verifier_sha256="${actual_authority_verifier_sha256%% *}"
if [[ "$actual_authority_verifier_sha256" != "$EXPECTED_AUTHORITY_VERIFIER_SHA256" ]]; then
  echo "wrapper-owned public edge authority verifier does not match its independent SHA-256 pin" >&2
  exit 2
fi
"$TRUSTED_ENV" -i \
  PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
  "$TRUSTED_PYTHON" -I "$TRUSTED_AUTHORITY_VERIFIER" \
  "${trusted_authority_args[@]}"

CANONICAL_BUILD_CONTEXT="/docker/chummercomplete"
CANONICAL_COMPOSE_PROJECT="chummer6-hub"
CANONICAL_INSTALL_LINKING_STATE_VOLUME="${CANONICAL_COMPOSE_PROJECT}_chummer-run-api-state"
CANONICAL_ENV_FILE="/docker/chummercomplete/chummer.run-services/.env"
CANONICAL_IMAGE_TAG="chummer-run-api:local"
CANONICAL_OVERLAY_ROOT="/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app"
CANONICAL_PUBLIC_EDGE_PORT="8091"
CANONICAL_BASE_URL="https://chummer.run"
CANONICAL_TUNNEL_PRIMARY_SERVICE="chummer-run-cloudflared"
CANONICAL_TUNNEL_REPLICA_SERVICE="chummer-run-cloudflared-replica"
CANONICAL_DOCKER_CONTEXT="default"
CANONICAL_DOCKER_HOST="unix:///var/run/docker.sock"
CANONICAL_DOCKER_CONFIG_ROOT="/docker/chummercomplete/.state/public-edge-docker-cli"
CANONICAL_FLEET_MEDIA_CONTRACTS="/docker/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts"
CANONICAL_DESIGN_PRODUCT_ROOT="/docker/chummercomplete/chummer-design"
CANONICAL_PUBLIC_PROJECTION_SNAPSHOT_ROOT="/docker/chummercomplete/chummer.run-services/.codex-studio/published"
CANONICAL_PUBLIC_DOWNLOAD_FLEET_SOURCE="/docker/fleet/.codex-studio/published"
CANONICAL_PUBLIC_DOWNLOAD_FINAL_GOLD_SOURCE="/docker/chummercomplete/chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json"
BUILD_CONTEXT="${CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT:-$CANONICAL_BUILD_CONTEXT}"
COMPOSE_FILE_INPUT="${CHUMMER_PUBLIC_EDGE_COMPOSE_FILE:-$ROOT_DIR/docker-compose.public-edge.yml}"
COMPOSE_PROJECT="${CHUMMER_PUBLIC_EDGE_PROJECT_NAME:-$CANONICAL_COMPOSE_PROJECT}"
ENV_FILE_INPUT="${CHUMMER_PUBLIC_EDGE_ENV_FILE:-$CANONICAL_ENV_FILE}"
IMAGE_TAG="${CHUMMER_PUBLIC_EDGE_PORTAL_IMAGE_TAG:-$CANONICAL_IMAGE_TAG}"
OVERLAY_ROOT="${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR:-$CANONICAL_OVERLAY_ROOT}"
BASE_URL="${CHUMMER_PUBLIC_EDGE_BASE_URL:-$CANONICAL_BASE_URL}"
RELEASE_CHANNEL_RECEIPT_INPUT="${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT-}"
RELEASE_CHANNEL_RECEIPT_SHA256="${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256-}"
PROJECTION_SNAPSHOT_ROOT_INPUT="${CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT-}"
PROJECTION_SNAPSHOT_TREE_SHA256="${CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_TREE_SHA256-}"
RUNTIME_PROOF_BIND_SOURCE_SHA256="${CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256-}"
INSTALL_LINKING_CUTOVER_BOUNDARY_INPUT="${CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY-}"
INSTALL_LINKING_CUTOVER_BOUNDARY_SHA256="${CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY_SHA256-}"
EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID="${CHUMMER_INSTALL_LINKING_CANDIDATE_IMAGE_ID-}"
EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID="${CHUMMER_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID-}"
INSTALL_LINKING_REPLAY_SYNTHETIC_WORKSPACE_ROOT="${CHUMMER_INSTALL_LINKING_REPLAY_SYNTHETIC_WORKSPACE_ROOT-}"
INSTALL_LINKING_REPLAY_BUILD_CONTEXT_ROOT="${CHUMMER_INSTALL_LINKING_REPLAY_BUILD_CONTEXT_ROOT-}"
INSTALL_LINKING_REPLAY_RUN_SERVICES_ROOT="${CHUMMER_INSTALL_LINKING_REPLAY_RUN_SERVICES_ROOT-}"
INSTALL_LINKING_REPLAY_HUB_REGISTRY_ROOT="${CHUMMER_INSTALL_LINKING_REPLAY_HUB_REGISTRY_ROOT-}"
INSTALL_LINKING_REPLAY_DESIGN_PRODUCT_ROOT="${CHUMMER_INSTALL_LINKING_REPLAY_DESIGN_PRODUCT_ROOT-}"
INSTALL_LINKING_REPLAY_FLEET_MEDIA_FACTORY_ROOT="${CHUMMER_INSTALL_LINKING_REPLAY_FLEET_MEDIA_FACTORY_ROOT-}"
FLEET_MEDIA_CONTRACTS="${CHUMMER_FLEET_MEDIA_CONTRACTS:-$CANONICAL_FLEET_MEDIA_CONTRACTS}"
DESIGN_PRODUCT_ROOT="${CHUMMER_DESIGN_PRODUCT_ROOT:-$CANONICAL_DESIGN_PRODUCT_ROOT}"
BUILD_CONCURRENCY="${CHUMMER_BUILD_CONCURRENCY:-1}"
POSTDEPLOY_OUTPUT="${CHUMMER_PUBLIC_EDGE_POSTDEPLOY_OUTPUT:-$SOURCE_ROOT/.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json}"
PLAYWRIGHT_ARTIFACT_DIR="${CHUMMER_PUBLIC_EDGE_PLAYWRIGHT_ARTIFACT_DIR:-$SOURCE_ROOT/.codex-studio/published/public-edge-browser-proofs}"
COMPOSE_ATTESTATION_OUTPUT="${CHUMMER_PUBLIC_EDGE_COMPOSE_ATTESTATION_OUTPUT:-$SOURCE_ROOT/.codex-studio/published/PUBLIC_EDGE_COMPOSE_RUNTIME_ATTESTATION.generated.json}"
PROGRESS="${CHUMMER_PUBLIC_EDGE_BUILD_PROGRESS:-auto}"
POSTDEPLOY_ATTEMPTS="${CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS:-3}"
POSTDEPLOY_RETRY_DELAY_SECONDS="${CHUMMER_PUBLIC_EDGE_POSTDEPLOY_RETRY_DELAY_SECONDS:-10}"
PORTAL_READY_TIMEOUT_SECONDS="${CHUMMER_PUBLIC_EDGE_PORTAL_READY_TIMEOUT_SECONDS:-180}"
PUBLIC_EDGE_PORT="${CHUMMER_PUBLIC_EDGE_PORT:-$CANONICAL_PUBLIC_EDGE_PORT}"
RELEASE_UPLOAD_TICKET_NEXT_EPOCH="${CHUMMER_RELEASE_UPLOAD_TICKET_REVOCATION_NEXT_EPOCH-}"
RELEASE_UPLOAD_OLD_TICKET_PATH="${CHUMMER_RELEASE_UPLOAD_OLD_TICKET_PATH-}"
RELEASE_UPLOAD_OLD_TICKET_AUTHORITY_INPUT="${CHUMMER_RELEASE_UPLOAD_OLD_TICKET_AUTHORITY-}"
RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_INPUT="${CHUMMER_RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT-}"
RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_EXPECTED_SHA256="${CHUMMER_RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256-}"
RELEASE_UPLOAD_TICKET_ENV_SHA256_BEFORE="${CHUMMER_RELEASE_UPLOAD_TICKET_ENV_SHA256_BEFORE-}"
RELEASE_UPLOAD_TICKET_EXPECTED_IMAGE_ID="${CHUMMER_RELEASE_UPLOAD_TICKET_EXPECTED_IMAGE_ID-}"
RELEASE_UPLOAD_TICKET_PROOF_BIND_SOURCE_INPUT="${CHUMMER_RELEASE_UPLOAD_TICKET_PROOF_BIND_SOURCE-}"
RELEASE_UPLOAD_TICKET_PROOF_BIND_SOURCE_SHA256="${CHUMMER_RELEASE_UPLOAD_TICKET_PROOF_BIND_SOURCE_SHA256-}"
RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_EXPECTED_SHA256="${CHUMMER_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_EXPECTED_SHA256-}"
RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_AUTHORITY_INPUT="${CHUMMER_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_AUTHORITY-}"
RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_AUTHORITY_SHA256="${CHUMMER_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_AUTHORITY_SHA256-}"
RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_EXPECTED_SHA256="${CHUMMER_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_SHA256-}"
RELEASE_UPLOAD_TICKET_EDGE_WAF_LOCAL_EVIDENCE_SOURCE_INPUT="${CHUMMER_RELEASE_UPLOAD_TICKET_EDGE_WAF_LOCAL_EVIDENCE_SOURCE-}"
RELEASE_UPLOAD_TICKET_EDGE_WAF_LOCAL_EVIDENCE_SOURCE_SHA256="${CHUMMER_RELEASE_UPLOAD_TICKET_EDGE_WAF_LOCAL_EVIDENCE_SOURCE_SHA256-}"
DEPLOY_LOCK_ROOT="/docker/chummercomplete/.state"
DEPLOY_LOCK_DIR="$DEPLOY_LOCK_ROOT/public-edge-mutation.lock"
CANONICAL_DEPLOY_LOCK_AUTH_ROOT="$DEPLOY_LOCK_ROOT/public-edge-lock-recovery-receipts"
CANONICAL_DEPLOY_RECEIPT_ROOT="$DEPLOY_LOCK_ROOT/public-edge-deploy-receipts"
CANONICAL_ACTIVE_RUNTIME_AUTHORITY="$CANONICAL_DEPLOY_RECEIPT_ROOT/active-runtime-authority.json"
CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_AUTHORITY="$CANONICAL_DEPLOY_RECEIPT_ROOT/release-upload-ticket-epoch-authority.json"
CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY="$CANONICAL_DEPLOY_RECEIPT_ROOT/release-upload-ticket-epoch-history.json"
CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER="$CANONICAL_DEPLOY_RECEIPT_ROOT/release-upload-ticket-epoch-bootstrap-marker.json"
PUBLIC_DOWNLOAD_ACTIVE_RUNTIME_AUTHORITY="$CANONICAL_DEPLOY_RECEIPT_ROOT/public-download-active-runtime-authority.json"
OVERLAY_PRIOR_STATE_OUTPUT="$CANONICAL_DEPLOY_RECEIPT_ROOT/active-overlay-transaction.json"
CUTOVER_STATE_ROOT="$CANONICAL_DEPLOY_RECEIPT_ROOT/initial-release-shelf-cutover"
PUBLIC_DOWNLOAD_CUTOVER_STATE_ROOT="$CANONICAL_DEPLOY_RECEIPT_ROOT/initial-release-shelf-public-download-cutover"
PUBLIC_DOWNLOAD_CANDIDATE_ROOT="$CANONICAL_DEPLOY_RECEIPT_ROOT/initial-release-shelf-public-download-candidate"
PUBLIC_DOWNLOAD_OPERATION_ID="${CHUMMER_PUBLIC_DOWNLOAD_OPERATION_ID-}"
PUBLIC_DOWNLOAD_OPERATION_ROOT="$CANONICAL_DEPLOY_RECEIPT_ROOT/chummer-public-download-$PUBLIC_DOWNLOAD_OPERATION_ID"
PUBLIC_DOWNLOAD_OPERATION_JOURNAL="$CANONICAL_DEPLOY_RECEIPT_ROOT/chummer-public-download-$PUBLIC_DOWNLOAD_OPERATION_ID.operation.json"
PUBLIC_DOWNLOAD_CONTROLLER="$SOURCE_ROOT/scripts/deploy_public_download_only_cutover.py"
PLAYWRIGHT_AUTHORITY_PREPARER="$SOURCE_ROOT/scripts/prepare_operation_playwright_authority.py"
CANONICAL_RELEASE_SHELF_ROOT="/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads"
CUTOVER_RECOVERY_REEXEC=0
CUTOVER_STEADY_HANDOFF=0
CUTOVER_STATE_CLASSIFICATION=""
RECOVERY_ROUTE_REQUESTED=0
epoch_rotation_fail_forward_required=0
epoch_rotation_precommit_refused=0
public_download_controller_may_have_started=0
if ((RELEASE_UPLOAD_TICKET_EPOCH_ROTATION == 1 \
  || RELEASE_UPLOAD_TICKET_EPOCH_ROTATION_RESUME == 1)); then
  if [[ ! "$RELEASE_UPLOAD_TICKET_NEXT_EPOCH" \
    =~ ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$ ]]; then
    echo "CHUMMER_RELEASE_UPLOAD_TICKET_REVOCATION_NEXT_EPOCH must be an explicit safe epoch literal" >&2
    exit 2
  fi
  if [[ "$RELEASE_UPLOAD_OLD_TICKET_PATH" != /* \
    || "$RELEASE_UPLOAD_OLD_TICKET_AUTHORITY_INPUT" != /* ]]; then
    echo "epoch rotation requires absolute owner-only old-ticket and materialization-authority paths" >&2
    exit 2
  fi
  if [[ "$RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_EXPECTED_SHA256" != absent \
    && ! "$RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_EXPECTED_SHA256" \
      =~ ^[0-9a-f]{64}$ ]]; then
    echo "epoch rotation requires an exact current history SHA-256 or the literal absent pin" >&2
    exit 2
  fi
  if [[ "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_AUTHORITY_INPUT" != /* \
    || ! "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_AUTHORITY_SHA256" \
      =~ ^[0-9a-f]{64}$ \
    || ( "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_EXPECTED_SHA256" != absent \
      && ! "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_EXPECTED_SHA256" \
        =~ ^[0-9a-f]{64}$ ) ]]; then
    echo "epoch rotation requires an absolute pinned bootstrap authority and an exact bootstrap marker SHA-256 or the literal absent pin" >&2
    exit 2
  fi
  if [[ "$RELEASE_UPLOAD_TICKET_EDGE_WAF_LOCAL_EVIDENCE_SOURCE_INPUT" != /* \
    || ! "$RELEASE_UPLOAD_TICKET_EDGE_WAF_LOCAL_EVIDENCE_SOURCE_SHA256" \
      =~ ^[0-9a-f]{64}$ ]]; then
    echo "epoch rotation requires absolute pinned local WAF evidence and its exact SHA-256; this is not live control-plane verification" >&2
    exit 2
  fi
fi
if ((RELEASE_UPLOAD_TICKET_EPOCH_ROTATION_RESUME == 1)); then
  RECOVERY_ROUTE_REQUESTED=1
  if [[ "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_INPUT" != /* \
    || ! "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_EXPECTED_SHA256" \
      =~ ^[0-9a-f]{64}$ \
    || ! "$RELEASE_UPLOAD_TICKET_ENV_SHA256_BEFORE" =~ ^[0-9a-f]{64}$ \
    || ! "$RELEASE_UPLOAD_TICKET_EXPECTED_IMAGE_ID" \
      =~ ^sha256:[0-9a-f]{64}$ \
    || "$RELEASE_UPLOAD_TICKET_PROOF_BIND_SOURCE_INPUT" != /* \
    || ! "$RELEASE_UPLOAD_TICKET_PROOF_BIND_SOURCE_SHA256" \
      =~ ^[0-9a-f]{64}$ ]]; then
    echo "epoch-rotation resume requires exact receipt, old environment, image, and proof authority pins" >&2
    exit 2
  fi
fi
if [[ "$DEPLOY_OPERATION" == recover \
  || "$DEPLOY_OPERATION" == recover-adopt-verified-prior-runtime-baseline \
  || "$DEPLOY_OPERATION" == initial-release-shelf-public-download-cutover-recover \
  || "$DEPLOY_OPERATION" == initial-release-shelf-public-download-cutover-retire \
  || -e "$OVERLAY_PRIOR_STATE_OUTPUT" || -L "$OVERLAY_PRIOR_STATE_OUTPUT" ]]; then
  RECOVERY_ROUTE_REQUESTED=1
fi
if [[ "$DEPLOY_OPERATION" == deploy \
    || "$DEPLOY_OPERATION" == release-upload-ticket-epoch-rotate \
    || "$DEPLOY_OPERATION" == initial-release-shelf-cutover ]] \
  && ((RECOVERY_ROUTE_REQUESTED == 0)) \
  && [[ -e "$PUBLIC_DOWNLOAD_ACTIVE_RUNTIME_AUTHORITY" \
    || -L "$PUBLIC_DOWNLOAD_ACTIVE_RUNTIME_AUTHORITY" ]]; then
  echo "canonical public edge mutation is blocked while topology-B downloads authority exists; run initial-release-shelf-public-download-cutover-retire with the exact committed operation id to restore its captured incumbent configuration" >&2
  exit 2
fi

if [[ "$COMPOSE_FILE_INPUT" != /* ]]; then
  COMPOSE_FILE_INPUT="$SOURCE_ROOT/$COMPOSE_FILE_INPUT"
fi
EXPECTED_COMPOSE_FILE_INPUT="$SOURCE_ROOT/docker-compose.public-edge.yml"
if [[ "$COMPOSE_FILE_INPUT" != "$EXPECTED_COMPOSE_FILE_INPUT" \
  || ! -f "$COMPOSE_FILE_INPUT" || -L "$COMPOSE_FILE_INPUT" \
  || ! -O "$COMPOSE_FILE_INPUT" \
  || "$("$TRUSTED_STAT" -c '%h' -- "$COMPOSE_FILE_INPUT")" != 1 ]]; then
  echo "public edge deploy requires the exact owner-controlled single-link Compose input" >&2
  exit 2
fi
if ! COMPOSE_FILE_MODE="$("$TRUSTED_STAT" -c '%a' -- "$COMPOSE_FILE_INPUT")" \
  || [[ ! "$COMPOSE_FILE_MODE" =~ ^[0-7]{3,4}$ ]] \
  || (( (8#$COMPOSE_FILE_MODE & 8#022) != 0 )); then
  echo "public edge deploy refuses a group- or world-writable Compose input" >&2
  exit 2
fi
if ! COMPOSE_FILE="$("$TRUSTED_REALPATH" -e -- "$COMPOSE_FILE_INPUT")"; then
  echo "public edge Compose file does not exist: $COMPOSE_FILE_INPUT" >&2
  exit 2
fi
CANONICAL_COMPOSE_FILE="$("$TRUSTED_REALPATH" -e -- "$SOURCE_ROOT/docker-compose.public-edge.yml")"
if [[ "$COMPOSE_FILE" != "$CANONICAL_COMPOSE_FILE" ]]; then
  echo "public edge deploy refuses a Compose file outside the audited source root" >&2
  exit 2
fi

if ! ENV_FILE="$("$TRUSTED_REALPATH" -e -- "$ENV_FILE_INPUT")"; then
  echo "canonical public edge environment file does not exist: $ENV_FILE_INPUT" >&2
  exit 2
fi
if [[ "$ENV_FILE" != "$CANONICAL_ENV_FILE" ]]; then
  echo "public edge deploy refuses a non-canonical Compose environment file" >&2
  exit 2
fi
if [[ "$COMPOSE_PROJECT" != "$CANONICAL_COMPOSE_PROJECT" ]]; then
  echo "public edge deploy refuses a non-canonical Compose project" >&2
  exit 2
fi
if [[ "$IMAGE_TAG" != "$CANONICAL_IMAGE_TAG" ]]; then
  echo "public edge deploy refuses a non-canonical portal image tag" >&2
  exit 2
fi
if [[ "$OVERLAY_ROOT" != "$CANONICAL_OVERLAY_ROOT" ]]; then
  echo "public edge deploy refuses a non-canonical portal overlay root" >&2
  exit 2
fi
if [[ "$BASE_URL" != "$CANONICAL_BASE_URL" ]]; then
  echo "public edge deploy refuses a non-canonical verification origin" >&2
  exit 2
fi
if [[ "$BUILD_CONTEXT" != "$CANONICAL_BUILD_CONTEXT" ]]; then
  echo "public edge deploy refuses a non-canonical build context" >&2
  exit 2
fi
if [[ "$FLEET_MEDIA_CONTRACTS" != "$CANONICAL_FLEET_MEDIA_CONTRACTS" ]]; then
  echo "public edge deploy refuses a non-canonical fleet media context" >&2
  exit 2
fi
if [[ "$DESIGN_PRODUCT_ROOT" != "$CANONICAL_DESIGN_PRODUCT_ROOT" ]]; then
  echo "public edge deploy refuses a non-canonical design product context" >&2
  exit 2
fi
if [[ "$PUBLIC_EDGE_PORT" != "$CANONICAL_PUBLIC_EDGE_PORT" ]]; then
  echo "public edge deploy refuses a non-canonical public portal port" >&2
  exit 2
fi
if [[ -z "$PROJECTION_SNAPSHOT_ROOT_INPUT" ]]; then
  echo "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT must be externally supplied" >&2
  exit 2
fi
if ! PROJECTION_SNAPSHOT_ROOT="$(
  "$TRUSTED_REALPATH" -e -- "$PROJECTION_SNAPSHOT_ROOT_INPUT"
)"; then
  echo "public projection snapshot root is missing" >&2
  exit 2
fi
if [[ "$PROJECTION_SNAPSHOT_ROOT" != "$CANONICAL_PUBLIC_PROJECTION_SNAPSHOT_ROOT" \
  || ! -d "$PROJECTION_SNAPSHOT_ROOT" || -L "$PROJECTION_SNAPSHOT_ROOT" \
  || ! -O "$PROJECTION_SNAPSHOT_ROOT" ]]; then
  echo "public edge deploy refuses an unsafe or non-canonical projection snapshot root" >&2
  exit 2
fi
PUBLIC_PROJECTION_SNAPSHOT_ID=""
PUBLIC_PROJECTION_SNAPSHOT_SHA256=""
PUBLIC_PROJECTION_MANIFEST_SHA256=""
PUBLIC_PROJECTION_STATUS=""
PUBLIC_PROJECTION_STAGE=""
RUNTIME_PROOF_BIND_SOURCE=""
AUTHENTICATED_RUNTIME_PROOF_SHA256=""
RELEASE_CHANNEL_RECEIPT=""
AUTHENTICATED_RELEASE_CHANNEL_SHA256=""
if ((RELEASE_UPLOAD_TICKET_EPOCH_ROTATION_RESUME == 1)); then
  if ! RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT="$(
    "$TRUSTED_REALPATH" -e -- "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_INPUT"
  )" \
    || [[ "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" \
      != "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_INPUT" \
      || ! -f "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" \
      || -L "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" \
      || ! -O "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" ]]; then
    echo "epoch-rotation resume receipt is unsafe or aliased" >&2
    exit 2
  fi
  if ! RUNTIME_PROOF_BIND_SOURCE="$(
    "$TRUSTED_REALPATH" -e -- "$RELEASE_UPLOAD_TICKET_PROOF_BIND_SOURCE_INPUT"
  )" \
    || [[ "$RUNTIME_PROOF_BIND_SOURCE" \
      != "$RELEASE_UPLOAD_TICKET_PROOF_BIND_SOURCE_INPUT" \
      || ! -f "$RUNTIME_PROOF_BIND_SOURCE" \
      || -L "$RUNTIME_PROOF_BIND_SOURCE" \
      || ! -O "$RUNTIME_PROOF_BIND_SOURCE" ]]; then
    echo "epoch-rotation resume proof authority is unsafe or noncanonical" >&2
    exit 2
  fi
  runtime_proof_resume_parent="$(
    "$TRUSTED_DIRNAME" -- "$RUNTIME_PROOF_BIND_SOURCE"
  )"
  runtime_proof_resume_projection_id="${runtime_proof_resume_parent##*/}"
  if [[ "${runtime_proof_resume_parent%/*}" != "$PROJECTION_SNAPSHOT_ROOT" \
    || ! "$runtime_proof_resume_projection_id" \
      =~ ^public-projection-[0-9a-f]{64}$ \
    || "${RUNTIME_PROOF_BIND_SOURCE##*/}" \
      != "HUB_LOCAL_RELEASE_PROOF.generated.json" ]]; then
    echo "epoch-rotation resume proof authority is outside an exact immutable projection" >&2
    exit 2
  fi
  runtime_proof_resume_sha256="$(
    "$TRUSTED_SHA256SUM" -- "$RUNTIME_PROOF_BIND_SOURCE"
  )"
  runtime_proof_resume_sha256="${runtime_proof_resume_sha256%% *}"
  if [[ "$runtime_proof_resume_sha256" \
    != "$RELEASE_UPLOAD_TICKET_PROOF_BIND_SOURCE_SHA256" ]]; then
    echo "epoch-rotation resume proof authority does not match its pin" >&2
    exit 2
  fi
  RUNTIME_PROOF_BIND_SOURCE_SHA256="$RELEASE_UPLOAD_TICKET_PROOF_BIND_SOURCE_SHA256"
fi
if ((RECOVERY_ROUTE_REQUESTED == 0)); then
if [[ ! "$RUNTIME_PROOF_BIND_SOURCE_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256 must be externally supplied as a lowercase SHA-256" >&2
  exit 2
fi

TRUSTED_PROJECTION_VERIFIER="$SOURCE_ROOT/scripts/release/verify_public_projection.py"
if [[ ! -f "$TRUSTED_PROJECTION_VERIFIER" || -L "$TRUSTED_PROJECTION_VERIFIER" ]]; then
  echo "audited public projection verifier is missing or symlinked" >&2
  exit 2
fi
projection_purpose="code-deploy"
projection_output_args=(
  --output-name HUB_LOCAL_RELEASE_PROOF.generated.json
  --output-name RELEASE_CHANNEL.generated.json
)
if ((PUBLIC_DOWNLOAD_ONLY_OPERATION == 1)); then
  projection_purpose="candidate-import"
  projection_output_args+=(
    --output-name RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json
  )
fi
if ! projection_resolution_json="$(
  "$TRUSTED_ENV" -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
    "$TRUSTED_PYTHON" -I "$TRUSTED_PROJECTION_VERIFIER" \
      --resolve-current "$PROJECTION_SNAPSHOT_ROOT" \
      --purpose "$projection_purpose" \
      "${projection_output_args[@]}"
)"; then
  echo "authenticated CURRENT public projection is unavailable" >&2
  exit 2
fi
if ! projection_binding="$(
  printf '%s' "$projection_resolution_json" \
    | "$TRUSTED_ENV" -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
      "$TRUSTED_PYTHON" -I -c '
import json, re, sys
payload = json.load(sys.stdin)
purpose = sys.argv[1]
outputs = payload.get("outputs") or {}
proof_output = outputs.get("HUB_LOCAL_RELEASE_PROOF.generated.json") or {}
release_output = outputs.get("RELEASE_CHANNEL.generated.json") or {}
candidate_output = outputs.get("RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json") or {}
snapshot_id = str(payload.get("snapshotId") or "")
snapshot_sha = str(payload.get("snapshotSha256") or "")
manifest_sha = str(payload.get("manifestSha256") or "")
status = str(payload.get("status") or "")
stage = str(payload.get("projectionStage") or "")
proof_path = str(proof_output.get("path") or "")
proof_digest = str(proof_output.get("sha256") or "")
release_path = str(release_output.get("path") or "")
release_digest = str(release_output.get("sha256") or "")
candidate_path = str(candidate_output.get("path") or "")
candidate_digest = str(candidate_output.get("sha256") or "")
valid_authority = (
    (
        purpose == "code-deploy"
        and payload.get("codeDeploymentAuthority") is True
        and status == "review_required"
        and stage == "code_deploy_review_required"
        and payload.get("releaseUploadAuthority") is False
        and payload.get("candidateImportAuthority") is False
    )
    or (
        purpose == "candidate-import"
        and payload.get("candidateImportAuthority") is True
        and payload.get("codeDeploymentAuthority") is False
        and payload.get("releaseUploadAuthority") is False
        and status == "candidate_import_ready"
        and stage == "candidate_import_ready"
        and candidate_output.get("name")
            == "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
        and re.fullmatch(r"[0-9a-f]{64}", candidate_digest) is not None
        and "|" not in candidate_path
    )
)
if (
    payload.get("contractName") != "chummer.public_projection_current/v1"
    or not valid_authority
    or proof_output.get("name") != "HUB_LOCAL_RELEASE_PROOF.generated.json"
    or release_output.get("name") != "RELEASE_CHANNEL.generated.json"
    or re.fullmatch(r"public-projection-[0-9a-f]{64}", snapshot_id) is None
    or snapshot_id != f"public-projection-{snapshot_sha}"
    or re.fullmatch(r"[0-9a-f]{64}", manifest_sha) is None
    or re.fullmatch(r"[0-9a-f]{64}", proof_digest) is None
    or re.fullmatch(r"[0-9a-f]{64}", release_digest) is None
    or "|" in proof_path
    or "|" in release_path
):
    raise SystemExit(1)
print(
    "|".join(
        (
            snapshot_id,
            snapshot_sha,
            manifest_sha,
            status,
            stage,
            proof_path,
            proof_digest,
            release_path,
            release_digest,
            candidate_path,
            candidate_digest,
        )
    ),
    end="",
)
' "$projection_purpose"
)"; then
  echo "authenticated CURRENT public projection resolution is malformed" >&2
  exit 2
fi
IFS='|' read -r PUBLIC_PROJECTION_SNAPSHOT_ID PUBLIC_PROJECTION_SNAPSHOT_SHA256 \
  PUBLIC_PROJECTION_MANIFEST_SHA256 PUBLIC_PROJECTION_STATUS \
  PUBLIC_PROJECTION_STAGE \
  RUNTIME_PROOF_BIND_SOURCE AUTHENTICATED_RUNTIME_PROOF_SHA256 \
  RELEASE_CHANNEL_RECEIPT AUTHENTICATED_RELEASE_CHANNEL_SHA256 \
  PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY \
  AUTHENTICATED_CANDIDATE_IMPORT_AUTHORITY_SHA256 \
  <<<"$projection_binding"
if [[ "$RUNTIME_PROOF_BIND_SOURCE" \
    != "$PROJECTION_SNAPSHOT_ROOT/$PUBLIC_PROJECTION_SNAPSHOT_ID/HUB_LOCAL_RELEASE_PROOF.generated.json" \
  || ! -f "$RUNTIME_PROOF_BIND_SOURCE" || -L "$RUNTIME_PROOF_BIND_SOURCE" \
  || ! -O "$RUNTIME_PROOF_BIND_SOURCE" \
  || "$AUTHENTICATED_RUNTIME_PROOF_SHA256" != "$RUNTIME_PROOF_BIND_SOURCE_SHA256" ]]; then
  echo "authenticated CURRENT runtime proof does not match its immutable deploy handoff" >&2
  exit 2
fi
if [[ "$RELEASE_CHANNEL_RECEIPT" \
    != "$PROJECTION_SNAPSHOT_ROOT/$PUBLIC_PROJECTION_SNAPSHOT_ID/RELEASE_CHANNEL.generated.json" \
  || ! -f "$RELEASE_CHANNEL_RECEIPT" || -L "$RELEASE_CHANNEL_RECEIPT" \
  || ! -O "$RELEASE_CHANNEL_RECEIPT" \
  || ! "$AUTHENTICATED_RELEASE_CHANNEL_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "authenticated CURRENT release channel is unavailable" >&2
  exit 2
fi
  if ((PUBLIC_DOWNLOAD_ONLY_OPERATION == 1)); then
    if [[ "$PUBLIC_PROJECTION_STATUS" != candidate_import_ready \
      || "$PUBLIC_PROJECTION_STAGE" != candidate_import_ready \
      || "$PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY" \
        != "$PROJECTION_SNAPSHOT_ROOT/$PUBLIC_PROJECTION_SNAPSHOT_ID/RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json" ]]; then
      echo "public-download cutover requires the bounded candidate-import snapshot" >&2
      exit 2
    fi
  elif [[ "$PUBLIC_PROJECTION_STATUS" != review_required \
    || "$PUBLIC_PROJECTION_STAGE" != code_deploy_review_required ]]; then
    echo "new public edge deploy requires the bounded review-required code-deploy snapshot" >&2
    exit 2
  fi
  if [[ -n "$RELEASE_CHANNEL_RECEIPT_INPUT" ]]; then
    if ! release_channel_receipt_override="$(
      "$TRUSTED_REALPATH" -e -- "$RELEASE_CHANNEL_RECEIPT_INPUT"
    )"; then
      echo "public edge release-channel receipt override is unavailable" >&2
      exit 2
    fi
    if [[ "$release_channel_receipt_override" != "$RELEASE_CHANNEL_RECEIPT" ]]; then
      echo "public edge release-channel receipt override is not the authenticated CURRENT output" >&2
      exit 2
    fi
  fi
  if [[ ! "$RELEASE_CHANNEL_RECEIPT_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
    echo "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256 must be independently supplied as a lowercase SHA-256" >&2
    exit 2
  fi
  actual_release_channel_receipt_sha256="$(
    "$TRUSTED_SHA256SUM" -- "$RELEASE_CHANNEL_RECEIPT"
  )"
  actual_release_channel_receipt_sha256="${actual_release_channel_receipt_sha256%% *}"
  if [[ "$AUTHENTICATED_RELEASE_CHANNEL_SHA256" != "$RELEASE_CHANNEL_RECEIPT_SHA256" \
    || "$actual_release_channel_receipt_sha256" != "$RELEASE_CHANNEL_RECEIPT_SHA256" ]]; then
    echo "public edge release-channel receipt does not match its independent SHA-256 pin" >&2
    exit 2
  fi
fi

OVERLAY_BASE="${OVERLAY_ROOT%/app}"
if [[ "$OVERLAY_BASE/app" != "$OVERLAY_ROOT" ]]; then
  echo "public edge overlay root must end in /app" >&2
  exit 2
fi
OVERLAY_STAGING_ROOT="${OVERLAY_BASE}-next/app"
OVERLAY_BACKUP_ROOT="${OVERLAY_BASE}-backups"
OVERLAY_BUILD_ROOT="${OVERLAY_BASE}-build"
TOOL_IMAGE_TAG="chummer-install-linking-postgres-tool:local"

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
if [[ ! "$BUILD_CONCURRENCY" =~ ^[1-9][0-9]*$ ]]; then
  echo "public edge build concurrency must be a positive integer" >&2
  exit 2
fi
case "$PROGRESS" in
  auto|plain|tty|rawjson|quiet) ;;
  *)
    echo "public edge Buildx progress must be an audited literal" >&2
    exit 2
    ;;
esac
if [[ ! "$COMPOSE_PROJECT" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "public edge Compose project must be a safe literal identifier" >&2
  exit 2
fi
"$TRUSTED_INSTALL" -d -m 0700 -- "$DEPLOY_LOCK_ROOT"
if [[ ! -d "$DEPLOY_LOCK_ROOT" || -L "$DEPLOY_LOCK_ROOT" \
  || ! -O "$DEPLOY_LOCK_ROOT" \
  || "$("$TRUSTED_REALPATH" -e -- "$DEPLOY_LOCK_ROOT")" \
    != "$DEPLOY_LOCK_ROOT" ]]; then
  echo "public edge deploy lock root is not a caller-owned directory" >&2
  exit 2
fi
"$TRUSTED_CHMOD" 0700 -- "$DEPLOY_LOCK_ROOT"
if [[ -L "$CANONICAL_DEPLOY_RECEIPT_ROOT" \
  || (-e "$CANONICAL_DEPLOY_RECEIPT_ROOT" \
    && (! -d "$CANONICAL_DEPLOY_RECEIPT_ROOT" \
      || ! -O "$CANONICAL_DEPLOY_RECEIPT_ROOT")) ]]; then
  echo "canonical public edge deploy receipt root is unsafe" >&2
  exit 70
fi
"$TRUSTED_INSTALL" -d -m 0700 -- "$CANONICAL_DEPLOY_RECEIPT_ROOT"
"$TRUSTED_CHMOD" 0700 -- "$CANONICAL_DEPLOY_RECEIPT_ROOT"
if [[ "$("$TRUSTED_REALPATH" -e -- "$CANONICAL_DEPLOY_RECEIPT_ROOT")" \
  != "$CANONICAL_DEPLOY_RECEIPT_ROOT" ]]; then
  echo "canonical public edge deploy receipt root contains a symlink component" >&2
  exit 70
fi

deploy_lock_wrapper_sha256="$("$TRUSTED_SHA256SUM" -- "$SCRIPT_PATH")"
deploy_lock_wrapper_sha256="${deploy_lock_wrapper_sha256%% *}"
deploy_lock_controller_sha256="$(
  printf '%064d' 0
)"
deploy_lock_operation_id=""
deploy_lock_operation_root=""
deploy_lock_operation_journal=""
if ((PUBLIC_DOWNLOAD_ONLY_OPERATION == 1)); then
  if [[ ! "$PUBLIC_DOWNLOAD_OPERATION_ID" \
    =~ ^[a-z0-9][a-z0-9-]{7,63}$ ]]; then
    echo "CHUMMER_PUBLIC_DOWNLOAD_OPERATION_ID must be the exact governed topology-B operation identifier" >&2
    exit 2
  fi
  if [[ "$PUBLIC_DOWNLOAD_OPERATION_ROOT" \
      != "$CANONICAL_DEPLOY_RECEIPT_ROOT/chummer-public-download-$PUBLIC_DOWNLOAD_OPERATION_ID" \
    || "$PUBLIC_DOWNLOAD_OPERATION_JOURNAL" \
      != "$CANONICAL_DEPLOY_RECEIPT_ROOT/chummer-public-download-$PUBLIC_DOWNLOAD_OPERATION_ID.operation.json" ]]; then
    echo "public-download lock binding paths are not exact and adjacent" >&2
    exit 70
  fi
  if [[ ! -f "$PUBLIC_DOWNLOAD_CONTROLLER" || -L "$PUBLIC_DOWNLOAD_CONTROLLER" \
    || ! -O "$PUBLIC_DOWNLOAD_CONTROLLER" \
    || "$("$TRUSTED_STAT" -c '%h' -- "$PUBLIC_DOWNLOAD_CONTROLLER")" != 1 ]]; then
    echo "audited public-download cutover controller is unsafe" >&2
    exit 2
  fi
  if ! public_download_controller_mode="$(
    "$TRUSTED_STAT" -c '%a' -- "$PUBLIC_DOWNLOAD_CONTROLLER"
  )" \
    || [[ ! "$public_download_controller_mode" =~ ^[0-7]{3,4}$ ]] \
    || (( (8#$public_download_controller_mode & 8#022) != 0 )); then
    echo "audited public-download cutover controller is group- or world-writable" >&2
    exit 2
  fi
  deploy_lock_controller_sha256="$(
    "$TRUSTED_SHA256SUM" -- "$PUBLIC_DOWNLOAD_CONTROLLER"
  )"
  deploy_lock_controller_sha256="${deploy_lock_controller_sha256%% *}"
  deploy_lock_operation_id="$PUBLIC_DOWNLOAD_OPERATION_ID"
  deploy_lock_operation_root="$PUBLIC_DOWNLOAD_OPERATION_ROOT"
  deploy_lock_operation_journal="$PUBLIC_DOWNLOAD_OPERATION_JOURNAL"
fi
if [[ ! "$deploy_lock_wrapper_sha256" =~ ^[0-9a-f]{64}$ \
  || ! "$deploy_lock_controller_sha256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "public edge deployment lock program digests are malformed" >&2
  exit 70
fi

"$TRUSTED_INSTALL" -d -m 0700 -- "$DEPLOY_LOCK_ROOT"
if [[ ! -d "$DEPLOY_LOCK_ROOT" || -L "$DEPLOY_LOCK_ROOT" || ! -O "$DEPLOY_LOCK_ROOT" \
  || "$("$TRUSTED_REALPATH" -e -- "$DEPLOY_LOCK_ROOT")" != "$DEPLOY_LOCK_ROOT" ]]; then
  echo "public edge deploy lock root is not a caller-owned directory" >&2
  exit 2
fi
"$TRUSTED_CHMOD" 0700 -- "$DEPLOY_LOCK_ROOT"
if [[ -L "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT" \
  || (-e "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT" \
    && (! -d "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT" || ! -O "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT")) ]]; then
  echo "public edge durable lock-authority root is unsafe" >&2
  exit 2
fi
"$TRUSTED_INSTALL" -d -m 0700 -- "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT"
"$TRUSTED_CHMOD" 0700 -- "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT"
if [[ "$("$TRUSTED_REALPATH" -e -- "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT")" \
  != "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT" ]]; then
  echo "public edge durable lock-authority root contains a symlink component" >&2
  exit 2
fi
lock_acquire_mode=acquire
if ((RELEASE_UPLOAD_TICKET_EPOCH_ROTATION_RESUME == 1)); then
  lock_acquire_mode=adopt
elif [[ "$DEPLOY_OPERATION" == recover ]]; then
  # A normal deploy can retain the authenticated lock together with the
  # overlay transaction when post-quiesce authority is unknown.  Recovery
  # must adopt that exact lock instead of competing with it.  Keep the
  # acquire path for older interrupted journals that no longer have a lock.
  lock_acquire_mode=acquire-or-adopt
elif [[ "$DEPLOY_OPERATION" \
    == initial-release-shelf-public-download-cutover ]]; then
  lock_acquire_mode=acquire-or-prestart-adopt
elif [[ "$DEPLOY_OPERATION" \
    == initial-release-shelf-public-download-cutover-recover ]]; then
  lock_acquire_mode=adopt
elif [[ "$DEPLOY_OPERATION" \
    == initial-release-shelf-public-download-cutover-retire ]]; then
  lock_acquire_mode=acquire-or-adopt
fi
if deploy_lock_metadata="$(
  "$TRUSTED_ENV" -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
    "$TRUSTED_PYTHON" -I -c '
import hashlib, hmac, json, os, re, secrets, stat, sys
lock_root = os.fsencode(sys.argv[1])
lock_path = os.fsencode(sys.argv[2])
authorization_root = os.fsencode(sys.argv[3])
mode = sys.argv[4]
requested_operation = sys.argv[5]
operation_id = sys.argv[6]
operation_root = sys.argv[7]
journal_path = sys.argv[8]
source_head = sys.argv[9].lower()
wrapper_sha256 = sys.argv[10]
controller_sha256 = sys.argv[11]
cutover_operation = "initial-release-shelf-public-download-cutover"
recovery_operation = "initial-release-shelf-public-download-cutover-recover"
retire_operation = "initial-release-shelf-public-download-cutover-retire"
deploy_operation = "deploy"
deploy_recovery_operation = "recover"
epoch_operation = "release-upload-ticket-epoch-rotate"
epoch_resume_operation = "release-upload-ticket-epoch-rotate-resume"
binding_contract = "chummer.public-edge-retained-lock-binding/v1"
journal_schema = "chummer.public-download-only-operation/v1"
sha256_pattern = re.compile(r"[0-9a-f]{64}")
commit_pattern = re.compile(r"[0-9a-f]{40}")
operation_id_pattern = re.compile(r"[a-z0-9][a-z0-9-]{7,63}")


def fail(status=70):
    raise SystemExit(status)


def full_identity(metadata):
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
    )


def pair(metadata):
    return f"{metadata.st_dev}:{metadata.st_ino}"


def binding_identity(metadata):
    return {"device": metadata.st_dev, "inode": metadata.st_ino}


def validate_private_directory(path, *, exact_mode=True):
    metadata = os.lstat(path)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or (
            exact_mode
            and stat.S_IMODE(metadata.st_mode) != 0o700
        )
        or (
            not exact_mode
            and stat.S_IMODE(metadata.st_mode) & 0o077
        )
        or os.path.realpath(path) != path
    ):
        fail()
    return metadata


def stable_regular(path, *, maximum, empty=False):
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        value = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    named = os.lstat(path)
    if (
        len({full_identity(item) for item in (before, after, named)}) != 1
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o600
        or len(value) > maximum
        or (empty and value != b"")
    ):
        fail()
    return value, before


def fsync_directories(*paths):
    for path in paths:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def validate_public_paths(*, require_operation_root):
    if (
        operation_id_pattern.fullmatch(operation_id) is None
        or b"|" in lock_root
        or "|" in operation_root
        or "|" in journal_path
    ):
        fail()
    receipt_root = os.path.join(lock_root, b"public-edge-deploy-receipts")
    validate_private_directory(receipt_root)
    expected_operation_root = os.path.join(
        os.fsdecode(receipt_root),
        f"chummer-public-download-{operation_id}",
    )
    expected_journal = f"{expected_operation_root}.operation.json"
    if (
        operation_root != expected_operation_root
        or journal_path != expected_journal
        or not os.path.isabs(operation_root)
        or os.path.normpath(operation_root) != operation_root
    ):
        fail()
    encoded_root = os.fsencode(operation_root)
    if os.path.lexists(encoded_root):
        validate_private_directory(encoded_root)
    elif require_operation_root:
        fail()


def load_journal(*, required, require_operation_root):
    validate_public_paths(require_operation_root=require_operation_root)
    encoded_journal = os.fsencode(journal_path)
    if not os.path.lexists(encoded_journal):
        if required:
            fail()
        return source_head
    raw, _metadata = stable_regular(
        encoded_journal,
        maximum=16 * 1024 * 1024,
    )
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        fail()
    journal_source_head = (
        payload.get("sourceHead") if isinstance(payload, dict) else None
    )
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != journal_schema
        or payload.get("operation") != cutover_operation
        or payload.get("projectName") != os.path.basename(operation_root)
        or payload.get("operationRoot") != operation_root
        or not isinstance(journal_source_head, str)
        or commit_pattern.fullmatch(journal_source_head) is None
    ):
        fail()
    return journal_source_head


def exact_binding_keys(payload):
    return set(payload) == {
        "allowedResumeOperation",
        "allowedPreControllerOperation",
        "contractName",
        "controllerSha256",
        "identities",
        "initialOperation",
        "journalPath",
        "journalSourceHead",
        "operationId",
        "operationRoot",
        "sourceHead",
        "tokenSha256",
        "wrapperSha256",
    } and set(payload.get("identities") or {}) == {
        "authorization",
        "binding",
        "lease",
        "lock",
        "token",
    }


for digest in (wrapper_sha256, controller_sha256):
    if sha256_pattern.fullmatch(digest) is None:
        fail()
if commit_pattern.fullmatch(source_head) is None:
    fail()
lock_root_stat = os.lstat(lock_root)
authorization_root_stat = os.lstat(authorization_root)
for metadata in (lock_root_stat, authorization_root_stat):
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        fail()
if mode == "acquire-or-adopt":
    mode = "adopt" if os.path.lexists(lock_path) else "acquire"
elif mode == "acquire-or-prestart-adopt":
    mode = (
        "adopt-prestart"
        if os.path.lexists(lock_path)
        else "acquire"
    )
if mode in {"adopt", "adopt-prestart"}:
    lock_stat = os.lstat(lock_path)
    if (
        not stat.S_ISDIR(lock_stat.st_mode)
        or stat.S_ISLNK(lock_stat.st_mode)
        or lock_stat.st_uid != os.getuid()
        or stat.S_IMODE(lock_stat.st_mode) != 0o700
        or os.listdir(lock_path) != [b"owner-token"]
    ):
        fail()
    token_path = os.path.join(lock_path, b"owner-token")
    token_raw, token_stat = stable_regular(
        token_path,
        maximum=65,
    )
    try:
        token = token_raw.decode("ascii", errors="strict").rstrip("\n")
    except UnicodeError:
        fail()
    if (
        token_raw not in {
            token.encode("ascii"),
            (token + "\n").encode("ascii"),
        }
        or len(token) != 64
        or any(character not in "0123456789abcdef" for character in token)
    ):
        fail()
    token_digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    authorization_path = os.path.join(
        authorization_root,
        f"deploy-{token_digest}.owner-token".encode("ascii"),
    )
    lease_path = os.path.join(
        authorization_root,
        f"deploy-{token_digest}.lease".encode("ascii"),
    )
    binding_path = os.path.join(
        authorization_root,
        f"deploy-{token_digest}.binding.json".encode("ascii"),
    )
    authorization_raw, authorization_stat = stable_regular(
        authorization_path,
        maximum=65,
    )
    _lease_raw, lease_stat = stable_regular(
        lease_path,
        maximum=0,
        empty=True,
    )
    binding_raw, binding_stat = stable_regular(
        binding_path,
        maximum=64 * 1024,
    )
    if not hmac.compare_digest(authorization_raw, token_raw):
        fail()
    try:
        binding = json.loads(binding_raw)
    except (UnicodeError, json.JSONDecodeError):
        fail()
    canonical_binding = (
        json.dumps(
            binding,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    normal_recovery_other_operation = (
        requested_operation == deploy_recovery_operation
        and (
            binding.get("initialOperation"),
            binding.get("allowedResumeOperation"),
        )
        in {
            (cutover_operation, recovery_operation),
            (retire_operation, retire_operation),
            (epoch_operation, epoch_resume_operation),
        }
    )
    if (
        not isinstance(binding, dict)
        or not exact_binding_keys(binding)
        or canonical_binding != binding_raw
        or token.encode("ascii") in binding_raw
        or binding.get("contractName") != binding_contract
        or binding.get("tokenSha256") != token_digest
        or binding.get("sourceHead") != source_head
        or binding.get("wrapperSha256") != wrapper_sha256
        or (
            binding.get("controllerSha256") != controller_sha256
            and not normal_recovery_other_operation
        )
        or binding["identities"].get("lock") != binding_identity(lock_stat)
        or binding["identities"].get("token") != binding_identity(token_stat)
        or binding["identities"].get("authorization")
        != binding_identity(authorization_stat)
        or binding["identities"].get("lease") != binding_identity(lease_stat)
        or binding["identities"].get("binding") != binding_identity(binding_stat)
    ):
        fail()
    if normal_recovery_other_operation:
        # Its own authenticated identity is intact, but a generic recovery is
        # not authorized to adopt this different governed operation.
        fail(75)
    expected_pair = (
        (cutover_operation, recovery_operation)
        if (
            mode == "adopt-prestart"
            and requested_operation == cutover_operation
        )
        else {
            deploy_recovery_operation: (
                deploy_operation,
                deploy_recovery_operation,
            ),
            recovery_operation: (cutover_operation, recovery_operation),
            retire_operation: (retire_operation, retire_operation),
            epoch_resume_operation: (
                epoch_operation,
                epoch_resume_operation,
            ),
        }.get(requested_operation)
    )
    if expected_pair is None:
        fail()
    expected_precontroller_operation = (
        cutover_operation
        if expected_pair[0] == cutover_operation
        else ""
    )
    if (
        binding.get("initialOperation") != expected_pair[0]
        or binding.get("allowedResumeOperation") != expected_pair[1]
        or binding.get("allowedPreControllerOperation")
            != expected_precontroller_operation
    ):
        fail()
    if mode == "adopt-prestart":
        validate_public_paths(require_operation_root=False)
        if (
            binding.get("allowedPreControllerOperation")
                != cutover_operation
            or binding.get("operationId") != operation_id
            or binding.get("operationRoot") != operation_root
            or binding.get("journalPath") != journal_path
            or binding.get("journalSourceHead") != source_head
        ):
            fail()
    elif requested_operation in {recovery_operation, retire_operation}:
        journal_source_head = load_journal(
            required=True,
            require_operation_root=requested_operation == retire_operation,
        )
        if (
            binding.get("operationId") != operation_id
            or binding.get("operationRoot") != operation_root
            or binding.get("journalPath") != journal_path
            or binding.get("journalSourceHead") != journal_source_head
        ):
            fail()
    elif any(
        binding.get(key) != ""
        for key in (
            "operationId",
            "operationRoot",
            "journalPath",
            "journalSourceHead",
        )
    ):
        fail()
    binding_sha256 = hashlib.sha256(binding_raw).hexdigest()
    adoption_kind = (
        "prestart" if mode == "adopt-prestart" else "retained"
    )
    print(
        f"{token}|{lock_stat.st_dev}:{lock_stat.st_ino}|"
        f"{token_stat.st_dev}:{token_stat.st_ino}|"
        f"{authorization_stat.st_dev}:{authorization_stat.st_ino}|"
        f"{os.fsdecode(authorization_path)}|"
        f"{lease_stat.st_dev}:{lease_stat.st_ino}|"
        f"{os.fsdecode(lease_path)}|"
        f"{binding_stat.st_dev}:{binding_stat.st_ino}|"
        f"{os.fsdecode(binding_path)}|{binding_sha256}|0||"
        f"{adoption_kind}"
    )
    raise SystemExit(0)
if mode != "acquire":
    fail()
if requested_operation in {
    recovery_operation,
    epoch_resume_operation,
}:
    fail()
allowed_precontroller_operation = ""
if requested_operation == cutover_operation:
    initial_operation = cutover_operation
    allowed_resume_operation = recovery_operation
    allowed_precontroller_operation = cutover_operation
    journal_source_head = load_journal(
        required=False,
        require_operation_root=False,
    )
    if journal_source_head != source_head:
        fail()
elif requested_operation == retire_operation:
    initial_operation = retire_operation
    allowed_resume_operation = retire_operation
    journal_source_head = load_journal(
        required=True,
        require_operation_root=True,
    )
else:
    initial_operation = requested_operation
    allowed_resume_operation = (
        deploy_recovery_operation
        if requested_operation == deploy_operation
        else (
            epoch_resume_operation
            if requested_operation == epoch_operation
            else ""
        )
    )
    operation_id = ""
    operation_root = ""
    journal_path = ""
    journal_source_head = ""
token = secrets.token_hex(32)
token_digest = hashlib.sha256(token.encode("ascii")).hexdigest()
staging_path = os.path.join(
    lock_root, f".public-edge-mutation.lock.staging.{token[:24]}".encode("ascii")
)
authorization_path = os.path.join(
    authorization_root, f"deploy-{token_digest}.owner-token".encode("ascii")
)
lease_path = os.path.join(
    authorization_root, f"deploy-{token_digest}.lease".encode("ascii")
)
binding_path = os.path.join(
    authorization_root, f"deploy-{token_digest}.binding.json".encode("ascii")
)
binding_temporary_path = os.path.join(
    authorization_root,
    f".deploy-{token_digest}.binding.{token[:24]}.tmp".encode("ascii"),
)
os.mkdir(staging_path, 0o700)
os.chmod(staging_path, 0o700)
staging_stat = os.lstat(staging_path)
token_path = os.path.join(staging_path, b"owner-token")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(token_path, flags, 0o600)
try:
    os.fchmod(descriptor, 0o600)
    os.write(descriptor, (token + "\n").encode("ascii"))
    os.fsync(descriptor)
    token_stat = os.fstat(descriptor)
finally:
    os.close(descriptor)
directory_descriptor = os.open(staging_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(directory_descriptor)
finally:
    os.close(directory_descriptor)
if (
    not stat.S_ISREG(token_stat.st_mode)
    or token_stat.st_nlink != 1
    or token_stat.st_uid != os.getuid()
    or stat.S_IMODE(token_stat.st_mode) != 0o600
):
    fail()
authorization_descriptor = os.open(authorization_path, flags, 0o600)
try:
    os.fchmod(authorization_descriptor, 0o600)
    os.write(authorization_descriptor, (token + "\n").encode("ascii"))
    os.fsync(authorization_descriptor)
    authorization_stat = os.fstat(authorization_descriptor)
finally:
    os.close(authorization_descriptor)
authorization_root_descriptor = os.open(
    authorization_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
)
try:
    os.fsync(authorization_root_descriptor)
finally:
    os.close(authorization_root_descriptor)
if (
    not stat.S_ISREG(authorization_stat.st_mode)
    or authorization_stat.st_nlink != 1
    or authorization_stat.st_uid != os.getuid()
    or stat.S_IMODE(authorization_stat.st_mode) != 0o600
):
    fail()
lease_descriptor = os.open(lease_path, flags, 0o600)
try:
    os.fchmod(lease_descriptor, 0o600)
    os.fsync(lease_descriptor)
    lease_stat = os.fstat(lease_descriptor)
finally:
    os.close(lease_descriptor)
if (
    not stat.S_ISREG(lease_stat.st_mode)
    or lease_stat.st_nlink != 1
    or lease_stat.st_uid != os.getuid()
    or stat.S_IMODE(lease_stat.st_mode) != 0o600
    or lease_stat.st_size != 0
):
    fail()
binding_descriptor = os.open(binding_temporary_path, flags, 0o600)
try:
    os.fchmod(binding_descriptor, 0o600)
    binding_stat = os.fstat(binding_descriptor)
    binding = {
        "allowedPreControllerOperation": allowed_precontroller_operation,
        "allowedResumeOperation": allowed_resume_operation,
        "contractName": binding_contract,
        "controllerSha256": controller_sha256,
        "identities": {
            "authorization": binding_identity(authorization_stat),
            "binding": binding_identity(binding_stat),
            "lease": binding_identity(lease_stat),
            "lock": binding_identity(staging_stat),
            "token": binding_identity(token_stat),
        },
        "initialOperation": initial_operation,
        "journalPath": journal_path,
        "journalSourceHead": journal_source_head,
        "operationId": operation_id,
        "operationRoot": operation_root,
        "sourceHead": source_head,
        "tokenSha256": token_digest,
        "wrapperSha256": wrapper_sha256,
    }
    binding_raw = (
        json.dumps(
            binding,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if token.encode("ascii") in binding_raw:
        fail()
    os.write(binding_descriptor, binding_raw)
    os.fsync(binding_descriptor)
    binding_after = os.fstat(binding_descriptor)
finally:
    os.close(binding_descriptor)
if (
    pair(binding_after) != pair(binding_stat)
    or not stat.S_ISREG(binding_after.st_mode)
    or binding_after.st_nlink != 1
    or binding_after.st_uid != os.getuid()
    or stat.S_IMODE(binding_after.st_mode) != 0o600
):
    fail()
os.link(binding_temporary_path, binding_path, follow_symlinks=False)
os.unlink(binding_temporary_path)
published_binding_stat = os.lstat(binding_path)
if pair(published_binding_stat) != pair(binding_stat):
    fail()
fsync_directories(authorization_root)
lock_stat = staging_stat
binding_sha256 = hashlib.sha256(binding_raw).hexdigest()
print(
    f"{token}|{lock_stat.st_dev}:{lock_stat.st_ino}|"
    f"{token_stat.st_dev}:{token_stat.st_ino}|"
    f"{authorization_stat.st_dev}:{authorization_stat.st_ino}|"
    f"{os.fsdecode(authorization_path)}|"
    f"{lease_stat.st_dev}:{lease_stat.st_ino}|"
    f"{os.fsdecode(lease_path)}|"
    f"{binding_stat.st_dev}:{binding_stat.st_ino}|"
    f"{os.fsdecode(binding_path)}|{binding_sha256}|1|"
    f"{os.fsdecode(staging_path)}|fresh"
)
' "$DEPLOY_LOCK_ROOT" "$DEPLOY_LOCK_DIR" "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT" \
    "$lock_acquire_mode" "$DEPLOY_OPERATION" "$deploy_lock_operation_id" \
    "$deploy_lock_operation_root" "$deploy_lock_operation_journal" \
    "${EXPECTED_HEAD,,}" "$deploy_lock_wrapper_sha256" \
    "$deploy_lock_controller_sha256"
)"; then
  :
else
  deploy_lock_acquire_status="$?"
  if [[ "$deploy_lock_acquire_status" == "75" ]]; then
    echo "another public-edge mutation owns the shared deployment authority" >&2
    exit 75
  fi
  echo "could not atomically establish authenticated public-edge deployment lock ownership" >&2
  exit 70
fi
IFS='|' read -r deploy_lock_owner_token deploy_lock_identity deploy_lock_token_identity \
  deploy_lock_auth_token_identity DEPLOY_LOCK_AUTH_TOKEN_FILE \
  deploy_lock_lease_identity DEPLOY_LOCK_LEASE_FILE \
  deploy_lock_binding_identity DEPLOY_LOCK_BINDING_FILE \
  deploy_lock_binding_sha256 deploy_lock_publish_required \
  deploy_lock_staging_path deploy_lock_adoption_kind \
  <<<"$deploy_lock_metadata"
deploy_lock_token_digest="$(
  printf '%s' "$deploy_lock_owner_token" | "$TRUSTED_SHA256SUM"
)"
deploy_lock_token_digest="${deploy_lock_token_digest%% *}"
deploy_lock_auth_token_name="${DEPLOY_LOCK_AUTH_TOKEN_FILE##*/}"
deploy_lock_lease_name="${DEPLOY_LOCK_LEASE_FILE##*/}"
deploy_lock_binding_name="${DEPLOY_LOCK_BINDING_FILE##*/}"
if [[ ! "$deploy_lock_owner_token" =~ ^[0-9a-f]{64}$ \
  || ! "$deploy_lock_identity" =~ ^[0-9]+:[0-9]+$ \
  || ! "$deploy_lock_token_identity" =~ ^[0-9]+:[0-9]+$ \
  || ! "$deploy_lock_auth_token_identity" =~ ^[0-9]+:[0-9]+$ \
  || ! "$deploy_lock_lease_identity" =~ ^[0-9]+:[0-9]+$ \
  || ! "$deploy_lock_binding_identity" =~ ^[0-9]+:[0-9]+$ \
  || ! "$deploy_lock_binding_sha256" =~ ^[0-9a-f]{64}$ \
  || ! "$deploy_lock_publish_required" =~ ^[01]$ \
  || ! "$deploy_lock_adoption_kind" =~ ^(fresh|retained|prestart)$ \
  || "${DEPLOY_LOCK_AUTH_TOKEN_FILE%/*}" != "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT" \
  || "${DEPLOY_LOCK_LEASE_FILE%/*}" != "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT" \
  || "${DEPLOY_LOCK_BINDING_FILE%/*}" != "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT" \
  || "$deploy_lock_auth_token_name" \
    != "deploy-$deploy_lock_token_digest.owner-token" \
  || "$deploy_lock_lease_name" != "deploy-$deploy_lock_token_digest.lease" \
  || "$deploy_lock_binding_name" \
    != "deploy-$deploy_lock_token_digest.binding.json" \
  || ( "$deploy_lock_publish_required" == 1 \
    && ( "${deploy_lock_staging_path%/*}" != "$DEPLOY_LOCK_ROOT" \
      || "${deploy_lock_staging_path##*/}" \
        != ".public-edge-mutation.lock.staging.${deploy_lock_owner_token:0:24}" ) ) \
  || ( "$deploy_lock_publish_required" == 0 \
    && -n "$deploy_lock_staging_path" ) \
  || ( "$deploy_lock_publish_required" == 1 \
    && "$deploy_lock_adoption_kind" != fresh ) \
  || ( "$deploy_lock_publish_required" == 0 \
    && "$deploy_lock_adoption_kind" == fresh ) \
  || ( "$deploy_lock_adoption_kind" == prestart \
    && "$DEPLOY_OPERATION" \
      != initial-release-shelf-public-download-cutover ) ]]; then
  echo "authenticated public-edge deployment lock metadata is malformed" >&2
  exit 70
fi
if ! exec {deploy_lock_lease_fd}<>"$DEPLOY_LOCK_LEASE_FILE"; then
  echo "authenticated public-edge deployment lock lease could not be opened" >&2
  exit 70
fi
validate_deploy_lock_lease_descriptor() {
  "$TRUSTED_ENV" -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
    "$TRUSTED_PYTHON" -I -c '
import os, stat, sys
descriptor = int(sys.argv[1])
path = os.fsencode(sys.argv[2])
expected_identity = sys.argv[3]
before = os.fstat(descriptor)
named = os.lstat(path)
after = os.fstat(descriptor)
identities = {
    (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mode,
        item.st_nlink,
        item.st_uid,
    )
    for item in (before, named, after)
}
if (
    len(identities) != 1
    or not stat.S_ISREG(before.st_mode)
    or before.st_nlink != 1
    or before.st_uid != os.getuid()
    or stat.S_IMODE(before.st_mode) != 0o600
    or before.st_size != 0
    or f"{before.st_dev}:{before.st_ino}" != expected_identity
):
    raise SystemExit(1)
' "$deploy_lock_lease_fd" "$DEPLOY_LOCK_LEASE_FILE" \
      "$deploy_lock_lease_identity"
}
if ! validate_deploy_lock_lease_descriptor; then
  exec {deploy_lock_lease_fd}>&-
  echo "authenticated public-edge deployment lock lease identity drifted" >&2
  exit 70
fi
if ! "$TRUSTED_FLOCK" --nonblock "$deploy_lock_lease_fd"; then
  exec {deploy_lock_lease_fd}>&-
  echo "another public-edge mutation owns the shared deployment authority" >&2
  exit 75
fi
if ! validate_deploy_lock_lease_descriptor; then
  exec {deploy_lock_lease_fd}>&-
  echo "authenticated public-edge deployment lock lease changed while acquired" >&2
  exit 70
fi
if [[ "$deploy_lock_adoption_kind" == prestart ]]; then
  if ! "$TRUSTED_ENV" -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
    "$TRUSTED_PYTHON" -I -c '
# Retained pre-controller public-download post-lease verifier.
import hashlib, json, os, re, stat, sys
receipt_root = os.fsencode(sys.argv[1])
operation_id = sys.argv[2]
operation_root = os.fsencode(sys.argv[3])
journal_path = os.fsencode(sys.argv[4])
binding_path = os.fsencode(sys.argv[5])
expected_binding_identity = sys.argv[6]
expected_binding_sha256 = sys.argv[7]
lease_descriptor = int(sys.argv[8])
lease_path = os.fsencode(sys.argv[9])
expected_lease_identity = sys.argv[10]
cutover_operation = "initial-release-shelf-public-download-cutover"


def fail():
    raise SystemExit(70)


def identity(metadata):
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
    )


def pair(metadata):
    return f"{metadata.st_dev}:{metadata.st_ino}"


def private_directory_identity(metadata):
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
    )


def stable_regular(path, expected_identity, maximum):
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        before = os.fstat(descriptor)
        value = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    named = os.lstat(path)
    if (
        len({identity(item) for item in (before, after, named)}) != 1
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o600
        or pair(before) != expected_identity
        or len(value) > maximum
    ):
        fail()
    return value


if (
    re.fullmatch(r"[a-z0-9][a-z0-9-]{7,63}", operation_id) is None
    or re.fullmatch(r"[0-9]+:[0-9]+", expected_binding_identity) is None
    or re.fullmatch(r"[0-9a-f]{64}", expected_binding_sha256) is None
    or re.fullmatch(r"[0-9]+:[0-9]+", expected_lease_identity) is None
):
    fail()
expected_operation_root = os.path.join(
    receipt_root,
    f"chummer-public-download-{operation_id}".encode("ascii"),
)
expected_journal = expected_operation_root + b".operation.json"
if (
    operation_root != expected_operation_root
    or journal_path != expected_journal
    or os.path.dirname(operation_root) != receipt_root
):
    fail()
receipt_descriptor = os.open(
    receipt_root,
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0),
)
try:
    receipt_before = os.fstat(receipt_descriptor)
    receipt_named = os.lstat(receipt_root)
    if (
        identity(receipt_before) != identity(receipt_named)
        or not stat.S_ISDIR(receipt_before.st_mode)
        or receipt_before.st_uid != os.getuid()
        or stat.S_IMODE(receipt_before.st_mode) != 0o700
        or os.path.realpath(receipt_root) != receipt_root
    ):
        fail()
    binding_raw = stable_regular(
        binding_path,
        expected_binding_identity,
        64 * 1024,
    )
    lease_named = os.lstat(lease_path)
    lease_open = os.fstat(lease_descriptor)
    if (
        identity(lease_named) != identity(lease_open)
        or not stat.S_ISREG(lease_open.st_mode)
        or lease_open.st_nlink != 1
        or lease_open.st_uid != os.getuid()
        or stat.S_IMODE(lease_open.st_mode) != 0o600
        or lease_open.st_size != 0
        or pair(lease_open) != expected_lease_identity
    ):
        fail()
    try:
        binding = json.loads(binding_raw)
    except (UnicodeError, json.JSONDecodeError):
        fail()
    if (
        hashlib.sha256(binding_raw).hexdigest()
            != expected_binding_sha256
        or not isinstance(binding, dict)
        or binding.get("initialOperation") != cutover_operation
        or binding.get("allowedPreControllerOperation")
            != cutover_operation
        or binding.get("operationId") != operation_id
        or os.fsencode(binding.get("operationRoot", "")) != operation_root
        or os.fsencode(binding.get("journalPath", "")) != journal_path
    ):
        fail()
    if os.path.lexists(journal_path):
        fail()
    if os.path.lexists(operation_root):
        operation_descriptor = os.open(
            operation_root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            operation_before = os.fstat(operation_descriptor)
            operation_named = os.lstat(operation_root)
            entries = os.listdir(operation_descriptor)
            operation_after = os.fstat(operation_descriptor)
            operation_named_after = os.lstat(operation_root)
            if (
                len(
                    {
                        identity(item)
                        for item in (
                            operation_before,
                            operation_named,
                            operation_after,
                            operation_named_after,
                        )
                    }
                ) != 1
                or not stat.S_ISDIR(operation_before.st_mode)
                or operation_before.st_uid != os.getuid()
                or stat.S_IMODE(operation_before.st_mode) != 0o700
                or os.path.realpath(operation_root) != operation_root
                or entries
                or os.path.lexists(journal_path)
            ):
                fail()
            os.rmdir(operation_root)
            os.fsync(receipt_descriptor)
        finally:
            os.close(operation_descriptor)
    receipt_after = os.fstat(receipt_descriptor)
    receipt_named_after = os.lstat(receipt_root)
    if (
        os.path.lexists(operation_root)
        or os.path.lexists(journal_path)
        or private_directory_identity(receipt_after)
            != private_directory_identity(receipt_before)
        or private_directory_identity(receipt_named_after)
            != private_directory_identity(receipt_before)
    ):
        fail()
finally:
    os.close(receipt_descriptor)
' "$CANONICAL_DEPLOY_RECEIPT_ROOT" "$PUBLIC_DOWNLOAD_OPERATION_ID" \
      "$PUBLIC_DOWNLOAD_OPERATION_ROOT" "$PUBLIC_DOWNLOAD_OPERATION_JOURNAL" \
      "$DEPLOY_LOCK_BINDING_FILE" "$deploy_lock_binding_identity" \
      "$deploy_lock_binding_sha256" "$deploy_lock_lease_fd" \
      "$DEPLOY_LOCK_LEASE_FILE" "$deploy_lock_lease_identity"; then
    exec {deploy_lock_lease_fd}>&-
    echo "retained pre-controller public-download authority changed after lease acquisition" >&2
    exit 70
  fi
fi
if [[ "$deploy_lock_publish_required" == 1 ]]; then
  if printf '%s\n' "$deploy_lock_owner_token" \
    | "$TRUSTED_ENV" -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
      "$TRUSTED_PYTHON" -I -c '
import ctypes, errno, hashlib, hmac, json, os, re, stat, sys
staging_path = os.fsencode(sys.argv[1])
lock_path = os.fsencode(sys.argv[2])
lock_root = os.fsencode(sys.argv[3])
authorization_root = os.fsencode(sys.argv[4])
expected_lock_identity = sys.argv[5]
expected_token_identity = sys.argv[6]
authorization_path = os.fsencode(sys.argv[7])
expected_authorization_identity = sys.argv[8]
lease_path = os.fsencode(sys.argv[9])
expected_lease_identity = sys.argv[10]
binding_path = os.fsencode(sys.argv[11])
expected_binding_identity = sys.argv[12]
expected_binding_sha256 = sys.argv[13]
lease_descriptor = int(sys.argv[14])
expected_token = sys.stdin.buffer.read(65).decode(
    "ascii",
    errors="strict",
).strip()
if (
    re.fullmatch(r"[0-9a-f]{64}", expected_token) is None
    or re.fullmatch(r"[0-9a-f]{64}", expected_binding_sha256) is None
):
    raise SystemExit(70)


def identity(metadata):
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
    )


def pair(metadata):
    return f"{metadata.st_dev}:{metadata.st_ino}"


def binding_identity(metadata):
    return {"device": metadata.st_dev, "inode": metadata.st_ino}


def stable_regular(path, expected_identity, maximum):
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        value = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    named = os.lstat(path)
    if (
        len({identity(item) for item in (before, after, named)}) != 1
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o600
        or pair(before) != expected_identity
        or len(value) > maximum
    ):
        raise SystemExit(70)
    return value, before


for directory in (lock_root, authorization_root):
    metadata = os.lstat(directory)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or os.path.realpath(directory) != directory
    ):
        raise SystemExit(70)
staging_stat = os.lstat(staging_path)
if (
    not stat.S_ISDIR(staging_stat.st_mode)
    or stat.S_ISLNK(staging_stat.st_mode)
    or staging_stat.st_uid != os.getuid()
    or stat.S_IMODE(staging_stat.st_mode) != 0o700
    or pair(staging_stat) != expected_lock_identity
    or os.path.realpath(staging_path) != staging_path
    or os.listdir(staging_path) != [b"owner-token"]
):
    raise SystemExit(70)
token_path = os.path.join(staging_path, b"owner-token")
token_raw, token_stat = stable_regular(
    token_path,
    expected_token_identity,
    65,
)
authorization_raw, authorization_stat = stable_regular(
    authorization_path,
    expected_authorization_identity,
    65,
)
lease_raw, lease_stat = stable_regular(
    lease_path,
    expected_lease_identity,
    0,
)
binding_raw, binding_stat = stable_regular(
    binding_path,
    expected_binding_identity,
    64 * 1024,
)
lease_descriptor_stat = os.fstat(lease_descriptor)
try:
    actual_token = token_raw.decode("ascii", errors="strict").strip()
    binding = json.loads(binding_raw)
except (UnicodeError, json.JSONDecodeError):
    raise SystemExit(70)
token_digest = hashlib.sha256(expected_token.encode("ascii")).hexdigest()
if (
    not hmac.compare_digest(actual_token, expected_token)
    or token_raw not in {
        expected_token.encode("ascii"),
        (expected_token + "\n").encode("ascii"),
    }
    or not hmac.compare_digest(authorization_raw, token_raw)
    or lease_raw != b""
    or identity(lease_descriptor_stat) != identity(lease_stat)
    or hashlib.sha256(binding_raw).hexdigest() != expected_binding_sha256
    or not isinstance(binding, dict)
    or not isinstance(binding.get("identities"), dict)
    or binding.get("contractName")
        != "chummer.public-edge-retained-lock-binding/v1"
    or binding.get("tokenSha256") != token_digest
    or binding["identities"].get("lock")
        != binding_identity(staging_stat)
    or binding["identities"].get("token")
        != binding_identity(token_stat)
    or binding["identities"].get("authorization")
        != binding_identity(authorization_stat)
    or binding["identities"].get("lease")
        != binding_identity(lease_stat)
    or binding["identities"].get("binding")
        != binding_identity(binding_stat)
    or expected_token.encode("ascii") in binding_raw
):
    raise SystemExit(70)
libc = ctypes.CDLL(None, use_errno=True)
renameat2 = getattr(libc, "renameat2", None)
if renameat2 is None:
    raise SystemExit(70)
renameat2.argtypes = [
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_uint,
]
renameat2.restype = ctypes.c_int
if renameat2(-100, staging_path, -100, lock_path, 1) != 0:
    error_number = ctypes.get_errno()
    if error_number != errno.EEXIST:
        raise OSError(
            error_number,
            os.strerror(error_number),
            os.fsdecode(lock_path),
        )
    os.unlink(token_path)
    os.rmdir(staging_path)
    os.unlink(binding_path)
    os.unlink(authorization_path)
    os.unlink(lease_path)
    for directory in (lock_root, authorization_root):
        descriptor = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    raise SystemExit(75)
published_lock_stat = os.lstat(lock_path)
published_token_stat = os.lstat(
    os.path.join(lock_path, b"owner-token")
)
if (
    pair(published_lock_stat) != expected_lock_identity
    or pair(published_token_stat) != expected_token_identity
):
    raise SystemExit(70)
descriptor = os.open(
    lock_root,
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
' "$deploy_lock_staging_path" "$DEPLOY_LOCK_DIR" "$DEPLOY_LOCK_ROOT" \
        "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT" "$deploy_lock_identity" \
        "$deploy_lock_token_identity" "$DEPLOY_LOCK_AUTH_TOKEN_FILE" \
        "$deploy_lock_auth_token_identity" "$DEPLOY_LOCK_LEASE_FILE" \
        "$deploy_lock_lease_identity" "$DEPLOY_LOCK_BINDING_FILE" \
        "$deploy_lock_binding_identity" "$deploy_lock_binding_sha256" \
        "$deploy_lock_lease_fd"; then
    :
  else
    deploy_lock_publish_status="$?"
    exec {deploy_lock_lease_fd}>&-
    if [[ "$deploy_lock_publish_status" == 75 ]]; then
      echo "another public-edge mutation owns the shared deployment authority" >&2
      exit 75
    fi
    echo "could not publish leased public-edge deployment lock ownership" >&2
    exit 70
  fi
fi
deploy_lock_was_adopted=0
adopted_public_download_controller_completed=0
if [[ "$deploy_lock_publish_required" == 0 ]]; then
  deploy_lock_was_adopted=1
fi
deploy_lock_active=1
if ((RELEASE_UPLOAD_TICKET_EPOCH_ROTATION_RESUME == 1)); then
  epoch_rotation_fail_forward_required=1
fi

release_deploy_lock() {
  if ((deploy_lock_active == 0)); then
    return 0
  fi
  if ! printf '%s\n' "$deploy_lock_owner_token" \
    | "$TRUSTED_ENV" -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
      "$TRUSTED_PYTHON" -I -c '
import ctypes, errno, hashlib, hmac, json, os, re, stat, sys
lock_path = os.fsencode(sys.argv[1])
expected_lock_identity = sys.argv[2]
expected_token_identity = sys.argv[3]
authorization_path = os.fsencode(sys.argv[4])
expected_authorization_identity = sys.argv[5]
lease_path = os.fsencode(sys.argv[6])
expected_lease_identity = sys.argv[7]
binding_path = os.fsencode(sys.argv[8])
expected_binding_identity = sys.argv[9]
expected_binding_sha256 = sys.argv[10]
lease_descriptor = int(sys.argv[11])
lock_root = os.path.dirname(lock_path)
authorization_root = os.path.dirname(authorization_path)
expected_token = sys.stdin.buffer.read(65).decode("ascii", errors="strict").strip()
if (
    re.fullmatch(r"[0-9a-f]{64}", expected_token) is None
    or re.fullmatch(r"[0-9a-f]{64}", expected_binding_sha256) is None
):
    raise SystemExit(1)


def identity(metadata):
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
    )


def pair(metadata):
    return f"{metadata.st_dev}:{metadata.st_ino}"


def binding_identity(metadata):
    return {"device": metadata.st_dev, "inode": metadata.st_ino}


def stable_regular(path, expected_identity, maximum):
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        value = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    named = os.lstat(path)
    if (
        len({identity(item) for item in (before, after, named)}) != 1
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o600
        or pair(before) != expected_identity
        or len(value) > maximum
    ):
        raise SystemExit(1)
    return value, before


for directory in (lock_root, authorization_root):
    metadata = os.lstat(directory)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or os.path.realpath(directory) != directory
    ):
        raise SystemExit(1)
lock_stat = os.lstat(lock_path)
if (
    not stat.S_ISDIR(lock_stat.st_mode)
    or stat.S_ISLNK(lock_stat.st_mode)
    or lock_stat.st_uid != os.getuid()
    or stat.S_IMODE(lock_stat.st_mode) != 0o700
    or f"{lock_stat.st_dev}:{lock_stat.st_ino}" != expected_lock_identity
    or os.listdir(lock_path) != [b"owner-token"]
):
    raise SystemExit(1)
token_path = os.path.join(lock_path, b"owner-token")
token_raw, token_stat = stable_regular(
    token_path,
    expected_token_identity,
    65,
)
authorization_raw, authorization_stat = stable_regular(
    authorization_path,
    expected_authorization_identity,
    65,
)
lease_raw, lease_stat = stable_regular(
    lease_path,
    expected_lease_identity,
    0,
)
binding_raw, binding_stat = stable_regular(
    binding_path,
    expected_binding_identity,
    64 * 1024,
)
lease_descriptor_stat = os.fstat(lease_descriptor)
try:
    actual_token = token_raw.decode("ascii", errors="strict").strip()
    binding = json.loads(binding_raw)
except (UnicodeError, json.JSONDecodeError):
    raise SystemExit(1)
token_digest = hashlib.sha256(expected_token.encode("ascii")).hexdigest()
if (
    not hmac.compare_digest(actual_token, expected_token)
    or token_raw not in {
        expected_token.encode("ascii"),
        (expected_token + "\n").encode("ascii"),
    }
    or not hmac.compare_digest(authorization_raw, token_raw)
    or lease_raw != b""
    or identity(lease_descriptor_stat) != identity(lease_stat)
    or hashlib.sha256(binding_raw).hexdigest() != expected_binding_sha256
    or not isinstance(binding, dict)
    or binding.get("contractName")
        != "chummer.public-edge-retained-lock-binding/v1"
    or binding.get("tokenSha256") != token_digest
    or not isinstance(binding.get("identities"), dict)
    or binding.get("identities", {}).get("lock")
        != binding_identity(lock_stat)
    or binding.get("identities", {}).get("token")
        != binding_identity(token_stat)
    or binding.get("identities", {}).get("authorization")
        != binding_identity(authorization_stat)
    or binding.get("identities", {}).get("lease")
        != binding_identity(lease_stat)
    or binding.get("identities", {}).get("binding")
        != binding_identity(binding_stat)
    or expected_token.encode("ascii") in binding_raw
):
    raise SystemExit(1)
releasing_path = os.path.join(
    lock_root,
    f"public-edge-mutation.lock.releasing.{token_digest}".encode("ascii"),
)
libc = ctypes.CDLL(None, use_errno=True)
renameat2 = getattr(libc, "renameat2", None)
if renameat2 is None:
    raise SystemExit(1)
renameat2.argtypes = [
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_uint,
]
renameat2.restype = ctypes.c_int
if renameat2(-100, lock_path, -100, releasing_path, 1) != 0:
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise SystemExit(1)
    raise OSError(
        error_number,
        os.strerror(error_number),
        os.fsdecode(lock_path),
    )
lock_root_descriptor = os.open(
    lock_root,
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
)
try:
    os.fsync(lock_root_descriptor)
finally:
    os.close(lock_root_descriptor)
released_lock_stat = os.lstat(releasing_path)
if (
    pair(released_lock_stat) != expected_lock_identity
    or not stat.S_ISDIR(released_lock_stat.st_mode)
    or stat.S_IMODE(released_lock_stat.st_mode) != 0o700
):
    raise SystemExit(1)
released_token_path = os.path.join(releasing_path, b"owner-token")
released_token_stat = os.lstat(released_token_path)
if pair(released_token_stat) != expected_token_identity:
    raise SystemExit(1)
os.unlink(released_token_path)
os.unlink(binding_path)
os.unlink(authorization_path)
os.unlink(lease_path)
os.rmdir(releasing_path)
for directory in (lock_root, authorization_root):
    directory_descriptor = os.open(
        directory,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
' "$DEPLOY_LOCK_DIR" "$deploy_lock_identity" "$deploy_lock_token_identity" \
        "$DEPLOY_LOCK_AUTH_TOKEN_FILE" "$deploy_lock_auth_token_identity" \
        "$DEPLOY_LOCK_LEASE_FILE" "$deploy_lock_lease_identity" \
        "$DEPLOY_LOCK_BINDING_FILE" "$deploy_lock_binding_identity" \
        "$deploy_lock_binding_sha256" "$deploy_lock_lease_fd"; then
    return 1
  fi
  deploy_lock_active=0
  exec {deploy_lock_lease_fd}>&-
}

release_only_on_exit() {
  local failure_status="$?"
  trap - EXIT
  if ((PUBLIC_DOWNLOAD_ONLY_OPERATION == 1 \
    && deploy_lock_was_adopted == 1 \
    && adopted_public_download_controller_completed == 0 \
    && deploy_lock_active == 1)); then
    deploy_lock_active=0
    echo "adopted public-download recovery did not complete; authenticated mutation lock retained" >&2
    exit 76
  fi
  if ((epoch_rotation_fail_forward_required == 1 \
    && deploy_lock_active == 1)); then
    deploy_lock_active=0
    echo "release-upload ticket epoch outcome is uncertain; authenticated mutation lock retained" >&2
    exit 76
  fi
  if ! release_deploy_lock; then
    echo "failed to release public edge deployment lock" >&2
    exit 70
  fi
  exit "$failure_status"
}

exit_for_signal() {
  local signal_status="$1"
  if ((epoch_rotation_fail_forward_required == 1 \
    && deploy_lock_active == 1)); then
    deploy_lock_active=0
    echo "release-upload ticket epoch rotation interrupted; authenticated mutation lock retained" >&2
    exit 76
  fi
  if ((PUBLIC_DOWNLOAD_ONLY_OPERATION == 1 \
      && public_download_controller_may_have_started == 1 \
      && deploy_lock_active == 1)); then
    deploy_lock_active=0
    echo "public-download journaled operation interrupted; authenticated mutation lock retained" >&2
    exit 76
  fi
  exit "$signal_status"
}

trap release_only_on_exit EXIT
trap 'exit_for_signal 129' HUP
trap 'exit_for_signal 130' INT
trap 'exit_for_signal 143' TERM

if [[ -L "$CANONICAL_DEPLOY_RECEIPT_ROOT" \
  || (-e "$CANONICAL_DEPLOY_RECEIPT_ROOT" \
    && (! -d "$CANONICAL_DEPLOY_RECEIPT_ROOT" || ! -O "$CANONICAL_DEPLOY_RECEIPT_ROOT")) ]]; then
  echo "canonical public edge deploy receipt root is unsafe" >&2
  exit 70
fi
"$TRUSTED_INSTALL" -d -m 0700 -- "$CANONICAL_DEPLOY_RECEIPT_ROOT"
"$TRUSTED_CHMOD" 0700 -- "$CANONICAL_DEPLOY_RECEIPT_ROOT"
if [[ "$("$TRUSTED_REALPATH" -e -- "$CANONICAL_DEPLOY_RECEIPT_ROOT")" \
  != "$CANONICAL_DEPLOY_RECEIPT_ROOT" ]]; then
  echo "canonical public edge deploy receipt root contains a symlink component" >&2
  exit 70
fi
if [[ -e "$OVERLAY_PRIOR_STATE_OUTPUT" || -L "$OVERLAY_PRIOR_STATE_OUTPUT" ]]; then
  RECOVERY_ROUTE_REQUESTED=1
fi
if ((PUBLIC_DOWNLOAD_ONLY_OPERATION == 1)); then
  PUBLIC_DOWNLOAD_CONTROLLER="$SOURCE_ROOT/scripts/deploy_public_download_only_cutover.py"
  PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_INPUT="${CHUMMER_PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY-}"
  PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_SHA256="${CHUMMER_PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_SHA256-}"
  PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT_INPUT="${CHUMMER_PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT-}"
  PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY_INPUT="${CHUMMER_PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY-}"
  PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY_SHA256="${CHUMMER_PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY_SHA256-}"
  PUBLIC_DOWNLOAD_SUCCESSOR_CUTOVER_AUTHORITY_INPUT="${CHUMMER_PUBLIC_DOWNLOAD_SUCCESSOR_CUTOVER_AUTHORITY-}"
  PUBLIC_DOWNLOAD_SUCCESSOR_CUTOVER_AUTHORITY_SHA256="${CHUMMER_PUBLIC_DOWNLOAD_SUCCESSOR_CUTOVER_AUTHORITY_SHA256-}"
  PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_INPUT="${CHUMMER_PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT-}"
  PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_SHA256="${CHUMMER_PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_SHA256-}"
  PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_ID="${CHUMMER_PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_ID-}"
  PUBLIC_DOWNLOAD_PREDECESSOR_RETIREMENT_RECEIPT_INPUT="${CHUMMER_PUBLIC_DOWNLOAD_PREDECESSOR_RETIREMENT_RECEIPT-}"
  PUBLIC_DOWNLOAD_PREDECESSOR_RETIREMENT_RECEIPT_SHA256="${CHUMMER_PUBLIC_DOWNLOAD_PREDECESSOR_RETIREMENT_RECEIPT_SHA256-}"
  PUBLIC_DOWNLOAD_SUCCESSOR_INPUT_COUNT=0
  PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_INPUT="${CHUMMER_PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT-}"
  PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_SHA256="${CHUMMER_PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_SHA256-}"
  PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_INPUT="${CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_FILE-}"
  PUBLIC_DOWNLOAD_CLOUDFLARE_ACCOUNT_ID="${CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_ACCOUNT_ID-}"
  PUBLIC_DOWNLOAD_CLOUDFLARE_TUNNEL_ID="${CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_TUNNEL_ID-}"
  PUBLIC_DOWNLOAD_RESTORATION_SPEC_INPUT="${CHUMMER_PUBLIC_DOWNLOAD_MANIFEST_CLOSURE_RESTORATION_SPEC-}"
  PUBLIC_DOWNLOAD_RESTORATION_SPEC_SHA256="${CHUMMER_PUBLIC_DOWNLOAD_MANIFEST_CLOSURE_RESTORATION_SPEC_SHA256-}"
  PUBLIC_DOWNLOAD_FINAL_GOLD_INPUT="${CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SOURCE:-$CANONICAL_PUBLIC_DOWNLOAD_FINAL_GOLD_SOURCE}"
  PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256="${CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256-}"
  PUBLIC_DOWNLOAD_FLEET_SOURCE_INPUT="${CHUMMER_PUBLIC_DOWNLOAD_FLEET_SOURCE:-$CANONICAL_PUBLIC_DOWNLOAD_FLEET_SOURCE}"
  PUBLIC_DOWNLOAD_FLEET_SHA256="${CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256-}"
  PUBLIC_DOWNLOAD_DELIVERY_PHASE="${CHUMMER_PUBLIC_DOWNLOAD_DELIVERY_PHASE-}"
  PUBLIC_DOWNLOAD_CANONICAL_PUBLISHER_SHA256="${CHUMMER_PUBLIC_DOWNLOAD_CANONICAL_PUBLISHER_SHA256-}"
  if [[ ! "$PUBLIC_DOWNLOAD_OPERATION_ID" \
    =~ ^[a-z0-9][a-z0-9-]{7,63}$ ]]; then
    echo "CHUMMER_PUBLIC_DOWNLOAD_OPERATION_ID must be the exact governed topology-B operation identifier" >&2
    exit 2
  fi
  if [[ "$DEPLOY_OPERATION" \
      == initial-release-shelf-public-download-cutover-retire ]] \
    && { [[ "$EXPECTED_UPSTREAM_REF" != refs/remotes/origin/main ]] \
      || [[ ! "$PUBLIC_DOWNLOAD_CANONICAL_PUBLISHER_SHA256" \
        =~ ^[0-9a-f]{64}$ ]]; }; then
    echo "topology-B retirement requires exact Hub main and the independently pinned canonical flagship publisher SHA-256" >&2
    exit 2
  fi
  if [[ ! -f "$PUBLIC_DOWNLOAD_CONTROLLER" || -L "$PUBLIC_DOWNLOAD_CONTROLLER" \
    || ! -O "$PUBLIC_DOWNLOAD_CONTROLLER" \
    || "$("$TRUSTED_STAT" -c '%h' -- "$PUBLIC_DOWNLOAD_CONTROLLER")" != 1 ]]; then
    echo "audited public-download cutover controller is unsafe" >&2
    exit 2
  fi
  if ! public_download_controller_mode="$("$TRUSTED_STAT" -c '%a' -- "$PUBLIC_DOWNLOAD_CONTROLLER")" \
    || [[ ! "$public_download_controller_mode" =~ ^[0-7]{3,4}$ ]] \
    || (( (8#$public_download_controller_mode & 8#022) != 0 )); then
    echo "audited public-download cutover controller is group- or world-writable" >&2
    exit 2
  fi
  if [[ ! "$PUBLIC_DOWNLOAD_CLOUDFLARE_ACCOUNT_ID" =~ ^[0-9a-f]{32}$ \
    || ! "$PUBLIC_DOWNLOAD_CLOUDFLARE_TUNNEL_ID" \
      =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
    echo "public-download Cloudflare account and tunnel identifiers are invalid" >&2
    exit 2
  fi
  if [[ "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_INPUT" != /* \
    || "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_INPUT" == *$'\n'* \
    || "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_INPUT" == *'|'* ]]; then
    echo "public-download Cloudflare credentials file path is required" >&2
    exit 2
  fi
  if ! PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS="$(
    "$TRUSTED_REALPATH" -e -- "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_INPUT"
  )" \
    || [[ "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS" \
      != "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_INPUT" ]]; then
    echo "public-download Cloudflare credentials file must use an exact canonical path" >&2
    exit 2
  fi
  if [[ ! -f "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS" \
    || -L "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS" \
    || ! -O "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS" \
    || ! -r "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS" \
    || "$("$TRUSTED_STAT" -c '%h' -- \
      "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS")" != 1 ]]; then
    echo "public-download Cloudflare credentials file metadata is unsafe" >&2
    exit 2
  fi
  if ! public_download_cloudflare_credentials_mode="$(
    "$TRUSTED_STAT" -c '%a' -- "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS"
  )" \
    || [[ ! "$public_download_cloudflare_credentials_mode" \
      =~ ^[0-7]{3,4}$ ]] \
    || (( (8#$public_download_cloudflare_credentials_mode & 8#077) != 0 )); then
    echo "public-download Cloudflare credentials file must be owner-only" >&2
    exit 2
  fi
  if ! public_download_cloudflare_credentials_size="$(
    "$TRUSTED_STAT" -c '%s' -- "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS"
  )" \
    || [[ ! "$public_download_cloudflare_credentials_size" =~ ^[0-9]+$ ]] \
    || ((public_download_cloudflare_credentials_size < 1 \
      || public_download_cloudflare_credentials_size > 65536)); then
    echo "public-download Cloudflare credentials file size is invalid" >&2
    exit 2
  fi
  if ((RECOVERY_ROUTE_REQUESTED == 0)); then
    if [[ "$PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_INPUT" != /* \
      || "$PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_INPUT" == *$'\n'* \
      || "$PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_INPUT" == *'|'* \
      || ! "$PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
      echo "public-download migration authority path and independent SHA-256 are required" >&2
      exit 2
    fi
    if [[ "$PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT_INPUT" != /* \
      || "$PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT_INPUT" == *$'\n'* \
      || "$PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT_INPUT" == *'|'* \
      || ! -d "$PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT_INPUT" \
      || -L "$PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT_INPUT" \
      || "$("$TRUSTED_REALPATH" -e -- \
        "$PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT_INPUT")" \
        != "$PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT_INPUT" ]]; then
      echo "public-download sealed release candidate root is unsafe" >&2
      exit 2
    fi
    PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT="$PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT_INPUT"
    if [[ "$PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY_INPUT" \
        != "$PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY" \
      || "$PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY_SHA256" \
        != "$AUTHENTICATED_CANDIDATE_IMPORT_AUTHORITY_SHA256" ]]; then
      echo "candidate-import authority does not match the authenticated projection snapshot" >&2
      exit 2
    fi
    if [[ "$PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_INPUT" \
        != "${PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT%/*}/UNSIGNED_WINDOWS_PREVIEW_DIRECT_IMPORT.generated.json" \
      || ! "$PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_SHA256" \
        =~ ^[0-9a-f]{64}$ \
      || ! -f "$PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_INPUT" \
      || -L "$PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_INPUT" \
      || ! -O "$PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_INPUT" \
      || "$("$TRUSTED_REALPATH" -e -- \
        "$PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_INPUT")" \
        != "$PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_INPUT" ]]; then
      echo "public-download direct-import receipt is unsafe or not adjacent to the bundle" >&2
      exit 2
    fi
    PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT="$PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_INPUT"
    public_download_successor_inputs=(
      "$PUBLIC_DOWNLOAD_SUCCESSOR_CUTOVER_AUTHORITY_INPUT"
      "$PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_INPUT"
      "$PUBLIC_DOWNLOAD_PREDECESSOR_RETIREMENT_RECEIPT_INPUT"
    )
    public_download_successor_digests=(
      "$PUBLIC_DOWNLOAD_SUCCESSOR_CUTOVER_AUTHORITY_SHA256"
      "$PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_SHA256"
      "$PUBLIC_DOWNLOAD_PREDECESSOR_RETIREMENT_RECEIPT_SHA256"
    )
    for public_download_successor_input in \
      "${public_download_successor_inputs[@]}"; do
      if [[ -n "$public_download_successor_input" ]]; then
        ((PUBLIC_DOWNLOAD_SUCCESSOR_INPUT_COUNT += 1))
      fi
    done
    for public_download_successor_digest in \
      "${public_download_successor_digests[@]}"; do
      if [[ -n "$public_download_successor_digest" ]]; then
        ((PUBLIC_DOWNLOAD_SUCCESSOR_INPUT_COUNT += 1))
      fi
    done
    if [[ -n "$PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_ID" ]]; then
      ((PUBLIC_DOWNLOAD_SUCCESSOR_INPUT_COUNT += 1))
    fi
    if ((PUBLIC_DOWNLOAD_SUCCESSOR_INPUT_COUNT != 0 \
      && PUBLIC_DOWNLOAD_SUCCESSOR_INPUT_COUNT != 7)); then
      echo "successor cutover authority inputs must be supplied together" >&2
      exit 2
    fi
    if ((PUBLIC_DOWNLOAD_SUCCESSOR_INPUT_COUNT == 7)); then
      if [[ ! "$PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_ID" \
        =~ ^[1-9][0-9]*$ ]]; then
        echo "successor decision artifact id is invalid" >&2
        exit 2
      fi
      for public_download_successor_index in 0 1 2; do
        public_download_successor_input="${public_download_successor_inputs[$public_download_successor_index]}"
        public_download_successor_digest="${public_download_successor_digests[$public_download_successor_index]}"
        if [[ "$public_download_successor_input" != /* \
          || "$public_download_successor_input" == *$'\n'* \
          || "$public_download_successor_input" == *'|'* \
          || ! "$public_download_successor_digest" =~ ^[0-9a-f]{64}$ \
          || ! -f "$public_download_successor_input" \
          || -L "$public_download_successor_input" \
          || ! -O "$public_download_successor_input" \
          || "$("$TRUSTED_STAT" -c '%h' -- \
            "$public_download_successor_input")" != 1 \
          || "$("$TRUSTED_REALPATH" -e -- \
            "$public_download_successor_input")" \
            != "$public_download_successor_input" ]]; then
          echo "successor cutover authority input is unsafe" >&2
          exit 2
        fi
        public_download_successor_observed_sha256="$(
          "$TRUSTED_SHA256SUM" -- "$public_download_successor_input"
        )"
        public_download_successor_observed_sha256="${public_download_successor_observed_sha256%% *}"
        if [[ "$public_download_successor_observed_sha256" \
          != "$public_download_successor_digest" ]]; then
          echo "successor cutover authority input SHA-256 drifted" >&2
          exit 2
        fi
      done
    fi
    if [[ ! "$PROJECTION_SNAPSHOT_TREE_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
      echo "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_TREE_SHA256 is required" >&2
      exit 2
    fi
    PUBLIC_DOWNLOAD_PROJECTION_AUTHORITY_ROOT="$PROJECTION_SNAPSHOT_ROOT"
    PUBLIC_DOWNLOAD_PROJECTION_SOURCE="$PROJECTION_SNAPSHOT_ROOT/$PUBLIC_PROJECTION_SNAPSHOT_ID"
    public_projection_current="$PROJECTION_SNAPSHOT_ROOT/CURRENT.json"
    if [[ ! -f "$public_projection_current" \
      || -L "$public_projection_current" \
      || ! -O "$public_projection_current" \
      || "$("$TRUSTED_STAT" -c '%a|%h' -- \
        "$public_projection_current")" != '644|1' ]]; then
      echo "authenticated public projection CURRENT metadata is unsafe" >&2
      exit 2
    fi
    PUBLIC_PROJECTION_CURRENT_SHA256="$(
      "$TRUSTED_SHA256SUM" -- "$public_projection_current"
    )" || {
      echo "authenticated public projection CURRENT could not be hashed" >&2
      exit 2
    }
    PUBLIC_PROJECTION_CURRENT_SHA256="${PUBLIC_PROJECTION_CURRENT_SHA256%% *}"
    if [[ ! "$PUBLIC_PROJECTION_CURRENT_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
      echo "authenticated public projection CURRENT digest is invalid" >&2
      exit 2
    fi
    if ! PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY="$(
      "$TRUSTED_REALPATH" -e -- "$PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_INPUT"
    )" \
      || [[ "$PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY" \
        != "$PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_INPUT" ]]; then
      echo "public-download migration authority must be an exact canonical path" >&2
      exit 2
    fi
    for public_download_file_input in \
      "$PUBLIC_DOWNLOAD_RESTORATION_SPEC_INPUT" \
      "$PUBLIC_DOWNLOAD_FINAL_GOLD_INPUT"; do
      if [[ "$public_download_file_input" != /* \
        || "$public_download_file_input" == *$'\n'* \
        || "$public_download_file_input" == *'|'* \
        || ! -f "$public_download_file_input" \
        || -L "$public_download_file_input" \
        || ! -O "$public_download_file_input" \
        || "$("$TRUSTED_STAT" -c '%h' -- "$public_download_file_input")" != 1 \
        || "$("$TRUSTED_REALPATH" -e -- "$public_download_file_input")" \
          != "$public_download_file_input" ]]; then
        echo "public-download file input is unsafe" >&2
        exit 2
      fi
    done
    if [[ ! "$PUBLIC_DOWNLOAD_RESTORATION_SPEC_SHA256" =~ ^[0-9a-f]{64}$ \
      || ! "$PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256" =~ ^[0-9a-f]{64}$ \
      || ! "$PUBLIC_DOWNLOAD_FLEET_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
      echo "public-download restoration/final-gold/fleet SHA-256 inputs are required" >&2
      exit 2
    fi
    if [[ "$PUBLIC_DOWNLOAD_FLEET_SOURCE_INPUT" != /* \
      || "$PUBLIC_DOWNLOAD_FLEET_SOURCE_INPUT" == *$'\n'* \
      || "$PUBLIC_DOWNLOAD_FLEET_SOURCE_INPUT" == *'|'* \
      || ! -d "$PUBLIC_DOWNLOAD_FLEET_SOURCE_INPUT" \
      || -L "$PUBLIC_DOWNLOAD_FLEET_SOURCE_INPUT" \
      || "$("$TRUSTED_REALPATH" -e -- "$PUBLIC_DOWNLOAD_FLEET_SOURCE_INPUT")" \
        != "$PUBLIC_DOWNLOAD_FLEET_SOURCE_INPUT" ]]; then
      echo "public-download fleet source is unsafe" >&2
      exit 2
    fi
    if [[ "$PUBLIC_DOWNLOAD_DELIVERY_PHASE" != "bootstrap" \
      && "$PUBLIC_DOWNLOAD_DELIVERY_PHASE" != "windows-preview" ]]; then
      echo "public-download delivery phase must be bootstrap or windows-preview" >&2
      exit 2
    fi
    PUBLIC_DOWNLOAD_RESTORATION_SPEC="$PUBLIC_DOWNLOAD_RESTORATION_SPEC_INPUT"
    PUBLIC_DOWNLOAD_FINAL_GOLD="$PUBLIC_DOWNLOAD_FINAL_GOLD_INPUT"
    PUBLIC_DOWNLOAD_FLEET_SOURCE="$PUBLIC_DOWNLOAD_FLEET_SOURCE_INPUT"
  else
    PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY="$PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_INPUT"
    PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT="${PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT_INPUT:-/nonexistent/topology-b-release-candidate}"
    PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY="${PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY_INPUT:-/nonexistent/topology-b-candidate-import-authority}"
    PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY_SHA256="${PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY_SHA256:-0000000000000000000000000000000000000000000000000000000000000000}"
    PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT="${PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_INPUT:-/nonexistent/topology-b-direct-import-receipt}"
    PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_SHA256="${PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_SHA256:-0000000000000000000000000000000000000000000000000000000000000000}"
    PUBLIC_DOWNLOAD_PROJECTION_AUTHORITY_ROOT="$PROJECTION_SNAPSHOT_ROOT"
    PUBLIC_DOWNLOAD_PROJECTION_SOURCE="${PROJECTION_SNAPSHOT_ROOT}/${PUBLIC_PROJECTION_SNAPSHOT_ID:-nonexistent-topology-b-projection}"
    PUBLIC_PROJECTION_CURRENT_SHA256="${PUBLIC_PROJECTION_CURRENT_SHA256:-0000000000000000000000000000000000000000000000000000000000000000}"
    PROJECTION_SNAPSHOT_TREE_SHA256="${PROJECTION_SNAPSHOT_TREE_SHA256:-0000000000000000000000000000000000000000000000000000000000000000}"
    PUBLIC_DOWNLOAD_RESTORATION_SPEC="${PUBLIC_DOWNLOAD_RESTORATION_SPEC_INPUT:-/nonexistent/topology-b-restoration-spec}"
    PUBLIC_DOWNLOAD_RESTORATION_SPEC_SHA256="${PUBLIC_DOWNLOAD_RESTORATION_SPEC_SHA256:-0000000000000000000000000000000000000000000000000000000000000000}"
    PUBLIC_DOWNLOAD_FINAL_GOLD="${PUBLIC_DOWNLOAD_FINAL_GOLD_INPUT:-/nonexistent/topology-b-final-gold}"
    PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256="${PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256:-0000000000000000000000000000000000000000000000000000000000000000}"
    PUBLIC_DOWNLOAD_FLEET_SOURCE="${PUBLIC_DOWNLOAD_FLEET_SOURCE_INPUT:-/nonexistent/topology-b-fleet}"
    PUBLIC_DOWNLOAD_FLEET_SHA256="${PUBLIC_DOWNLOAD_FLEET_SHA256:-0000000000000000000000000000000000000000000000000000000000000000}"
    PUBLIC_DOWNLOAD_DELIVERY_PHASE="${PUBLIC_DOWNLOAD_DELIVERY_PHASE:-windows-preview}"
  fi
  if [[ -L "$CANONICAL_DOCKER_CONFIG_ROOT" \
    || (-e "$CANONICAL_DOCKER_CONFIG_ROOT" \
      && (! -d "$CANONICAL_DOCKER_CONFIG_ROOT" || ! -O "$CANONICAL_DOCKER_CONFIG_ROOT")) ]]; then
    echo "canonical public edge Docker configuration root is unsafe" >&2
    exit 2
  fi
  "$TRUSTED_INSTALL" -d -m 0700 -- \
    "$CANONICAL_DOCKER_CONFIG_ROOT" \
    "$CANONICAL_DOCKER_CONFIG_ROOT/home" \
    "$CANONICAL_DOCKER_CONFIG_ROOT/config"
  "$TRUSTED_CHMOD" 0700 -- \
    "$CANONICAL_DOCKER_CONFIG_ROOT" \
    "$CANONICAL_DOCKER_CONFIG_ROOT/home" \
    "$CANONICAL_DOCKER_CONFIG_ROOT/config"
  public_download_controller_args=(
    --operation "$DEPLOY_OPERATION"
    --source-root "$SOURCE_ROOT"
    --source-head "${EXPECTED_HEAD,,}"
    --shared-mutation-lock-token "$deploy_lock_owner_token"
    --shelf-root "$CANONICAL_RELEASE_SHELF_ROOT"
    --migration-candidate-root "$PUBLIC_DOWNLOAD_CANDIDATE_ROOT"
    --migration-authority "$PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY"
    --migration-authority-sha256 "$PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_SHA256"
    --release-candidate-root "$PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT"
    --candidate-import-authority "$PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY"
    --candidate-import-authority-sha256 "$PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY_SHA256"
    --direct-import-receipt "$PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT"
    --direct-import-receipt-sha256 "$PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_SHA256"
    --manifest-closure-restoration-spec "$PUBLIC_DOWNLOAD_RESTORATION_SPEC"
    --manifest-closure-restoration-spec-sha256 "$PUBLIC_DOWNLOAD_RESTORATION_SPEC_SHA256"
    --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT"
    --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256"
    --projection-authority-root "$PUBLIC_DOWNLOAD_PROJECTION_AUTHORITY_ROOT"
    --projection-current-sha256 "$PUBLIC_PROJECTION_CURRENT_SHA256"
    --projection-snapshot-root "$PUBLIC_DOWNLOAD_PROJECTION_SOURCE"
    --projection-snapshot-id "$PUBLIC_PROJECTION_SNAPSHOT_ID"
    --projection-snapshot-sha256 "$PUBLIC_PROJECTION_SNAPSHOT_SHA256"
    --projection-snapshot-tree-sha256 "$PROJECTION_SNAPSHOT_TREE_SHA256"
    --projection-manifest-sha256 "$PUBLIC_PROJECTION_MANIFEST_SHA256"
    --runtime-proof-source "$RUNTIME_PROOF_BIND_SOURCE"
    --runtime-proof-sha256 "$RUNTIME_PROOF_BIND_SOURCE_SHA256"
    --final-gold-source "$PUBLIC_DOWNLOAD_FINAL_GOLD"
    --final-gold-sha256 "$PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256"
    --fleet-source "$PUBLIC_DOWNLOAD_FLEET_SOURCE"
    --fleet-sha256 "$PUBLIC_DOWNLOAD_FLEET_SHA256"
    --operation-root "$PUBLIC_DOWNLOAD_OPERATION_ROOT"
    --active-runtime-authority "$PUBLIC_DOWNLOAD_ACTIVE_RUNTIME_AUTHORITY"
    --docker-config-root "$CANONICAL_DOCKER_CONFIG_ROOT"
    --cloudflare-credentials-file "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS"
    --cloudflare-account-id "$PUBLIC_DOWNLOAD_CLOUDFLARE_ACCOUNT_ID"
    --cloudflare-tunnel-id "$PUBLIC_DOWNLOAD_CLOUDFLARE_TUNNEL_ID"
    --receipt-root "$CANONICAL_DEPLOY_RECEIPT_ROOT"
    --base-url "$BASE_URL"
    --canonical-publisher-sha256 "$PUBLIC_DOWNLOAD_CANONICAL_PUBLISHER_SHA256"
    --build-context "$BUILD_CONTEXT"
    --fleet-media-contracts "$FLEET_MEDIA_CONTRACTS"
    --design-product-root "$DESIGN_PRODUCT_ROOT"
    --delivery-phase "$PUBLIC_DOWNLOAD_DELIVERY_PHASE"
    --ready-timeout-seconds "$PORTAL_READY_TIMEOUT_SECONDS"
  )
  if ((PUBLIC_DOWNLOAD_SUCCESSOR_INPUT_COUNT == 7)); then
    public_download_controller_args+=(
      --successor-cutover-authority \
        "$PUBLIC_DOWNLOAD_SUCCESSOR_CUTOVER_AUTHORITY_INPUT"
      --successor-cutover-authority-sha256 \
        "$PUBLIC_DOWNLOAD_SUCCESSOR_CUTOVER_AUTHORITY_SHA256"
      --operator-decision-artifact \
        "$PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_INPUT"
      --operator-decision-artifact-sha256 \
        "$PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_SHA256"
      --operator-decision-artifact-id \
        "$PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_ID"
      --predecessor-retirement-receipt \
        "$PUBLIC_DOWNLOAD_PREDECESSOR_RETIREMENT_RECEIPT_INPUT"
      --predecessor-retirement-receipt-sha256 \
        "$PUBLIC_DOWNLOAD_PREDECESSOR_RETIREMENT_RECEIPT_SHA256"
    )
  fi
  public_download_wrapper_sha256="$(
    "$TRUSTED_SHA256SUM" -- "$SCRIPT_PATH"
  )"
  public_download_wrapper_sha256="${public_download_wrapper_sha256%% *}"
  public_download_controller_sha256="$(
    "$TRUSTED_SHA256SUM" -- "$PUBLIC_DOWNLOAD_CONTROLLER"
  )"
  public_download_controller_sha256="${public_download_controller_sha256%% *}"
  if [[ "$public_download_wrapper_sha256" \
      != "$deploy_lock_wrapper_sha256" \
    || "$public_download_controller_sha256" \
      != "$deploy_lock_controller_sha256" ]]; then
    echo "public-download lock-bound wrapper or controller digest drifted" >&2
    exit 70
  fi
  if ! exec {public_download_controller_fd}<"$PUBLIC_DOWNLOAD_CONTROLLER"; then
    echo "public-download lock-bound controller could not be opened" >&2
    exit 70
  fi
  if ! "$TRUSTED_ENV" -i \
    PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
    CHUMMER_PUBLIC_EDGE_BOUND_CONTROLLER_PATH="$PUBLIC_DOWNLOAD_CONTROLLER" \
    "$TRUSTED_PYTHON" -I -c '
import hashlib, os, stat, sys
# Public-download pinned controller descriptor verifier.
descriptor = int(sys.argv[1])
path = os.fsencode(
    os.environ.pop("CHUMMER_PUBLIC_EDGE_BOUND_CONTROLLER_PATH")
)
expected_sha256 = sys.argv[2]
before = os.fstat(descriptor)
named_before = os.lstat(path)
os.lseek(descriptor, 0, os.SEEK_SET)
digest = hashlib.sha256()
size = 0
while True:
    chunk = os.read(descriptor, 1024 * 1024)
    if not chunk:
        break
    size += len(chunk)
    if size > 16 * 1024 * 1024:
        raise SystemExit(1)
    digest.update(chunk)
os.lseek(descriptor, 0, os.SEEK_SET)
after = os.fstat(descriptor)
named_after = os.lstat(path)
identity = lambda item: (
    item.st_dev,
    item.st_ino,
    item.st_size,
    item.st_mtime_ns,
    item.st_ctime_ns,
    item.st_mode,
    item.st_nlink,
    item.st_uid,
)
if (
    len({
        identity(item)
        for item in (before, named_before, after, named_after)
    }) != 1
    or not stat.S_ISREG(before.st_mode)
    or before.st_nlink != 1
    or before.st_uid != os.getuid()
    or stat.S_IMODE(before.st_mode) & 0o022
    or size != before.st_size
    or digest.hexdigest() != expected_sha256
):
    raise SystemExit(1)
' "$public_download_controller_fd" "$deploy_lock_controller_sha256"; then
    exec {public_download_controller_fd}<&-
    echo "public-download lock-bound controller descriptor drifted" >&2
    exit 70
  fi
  public_download_controller_status=0
  public_download_controller_may_have_started=1
  "$TRUSTED_ENV" -i \
    PATH=/usr/bin:/bin LANG=C LC_ALL=C \
    CHUMMER_PUBLIC_EDGE_DEPLOY_LEASE_FD="$deploy_lock_lease_fd" \
    "$TRUSTED_PYTHON" -I -c '
import hashlib, os, stat, sys
controller_path = sys.argv[1]
descriptor = int(sys.argv[2])
expected_sha256 = sys.argv[3]
controller_arguments = sys.argv[4:]
metadata = os.fstat(descriptor)
if (
    not stat.S_ISREG(metadata.st_mode)
    or metadata.st_nlink != 1
    or metadata.st_uid != os.getuid()
    or stat.S_IMODE(metadata.st_mode) & 0o022
    or metadata.st_size > 16 * 1024 * 1024
):
    raise SystemExit(70)
os.lseek(descriptor, 0, os.SEEK_SET)
chunks = []
remaining = metadata.st_size + 1
while remaining > 0:
    chunk = os.read(descriptor, min(1024 * 1024, remaining))
    if not chunk:
        break
    chunks.append(chunk)
    remaining -= len(chunk)
raw = b"".join(chunks)
after = os.fstat(descriptor)
if (
    len(raw) != metadata.st_size
    or (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
    )
    != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_mode,
        after.st_nlink,
        after.st_uid,
    )
    or hashlib.sha256(raw).hexdigest() != expected_sha256
):
    raise SystemExit(70)
code = compile(raw, controller_path, "exec")
sys.argv = [controller_path, *controller_arguments]
namespace = globals()
namespace.update({
    "__cached__": None,
    "__doc__": None,
    "__file__": controller_path,
    "__loader__": None,
    "__name__": "__main__",
    "__package__": None,
    "__spec__": None,
})
exec(code, namespace, namespace)
' "$PUBLIC_DOWNLOAD_CONTROLLER" "$public_download_controller_fd" \
    "$deploy_lock_controller_sha256" \
    "${public_download_controller_args[@]}" \
    || public_download_controller_status=$?
  exec {public_download_controller_fd}<&-
  if ((public_download_controller_status == 76)) \
    || [[ "$DEPLOY_OPERATION" \
      == initial-release-shelf-public-download-cutover-retire \
      && "$public_download_controller_status" != 0 ]]; then
    deploy_lock_active=0
    echo "public-download journaled operation is uncertain; authenticated mutation lock retained" >&2
    exit 76
  fi
  if ((public_download_controller_status != 0)); then
    echo "public-download cutover, recovery, or retirement failed" >&2
    exit "$public_download_controller_status"
  fi
  adopted_public_download_controller_completed=1
  if ! release_deploy_lock; then
    deploy_lock_active=0
    trap - EXIT
    echo "public-download journaled operation completed but deployment lock release failed" >&2
    exit 70
  fi
  trap - EXIT
  exit 0
fi
INSTALL_LINKING_CUTOVER_BOUNDARY=""
if ((RECOVERY_ROUTE_REQUESTED == 0)); then
  if [[ "$INSTALL_LINKING_CUTOVER_BOUNDARY_INPUT" != /* \
    || "$INSTALL_LINKING_CUTOVER_BOUNDARY_INPUT" == *$'\n'* \
    || "$INSTALL_LINKING_CUTOVER_BOUNDARY_INPUT" == *'|'* ]]; then
    echo "CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY must be an absolute private receipt path" >&2
    exit 2
  fi
  if [[ ! "$INSTALL_LINKING_CUTOVER_BOUNDARY_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
    echo "CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY_SHA256 must be an independently supplied lowercase SHA-256" >&2
    exit 2
  fi
  if [[ ! "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "CHUMMER_INSTALL_LINKING_CANDIDATE_IMAGE_ID must be an independently supplied full image ID" >&2
    exit 2
  fi
  if [[ ! "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "CHUMMER_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID must be an independently supplied full image ID" >&2
    exit 2
  fi
  if ! INSTALL_LINKING_CUTOVER_BOUNDARY="$(
    "$TRUSTED_REALPATH" -e -- "$INSTALL_LINKING_CUTOVER_BOUNDARY_INPUT"
  )" \
    || [[ "$INSTALL_LINKING_CUTOVER_BOUNDARY" \
      != "$INSTALL_LINKING_CUTOVER_BOUNDARY_INPUT" ]]; then
    echo "InstallLinking cutover boundary must be an exact existing non-aliased path" >&2
    exit 2
  fi
fi
if ((RELEASE_UPLOAD_TICKET_EPOCH_ROTATION_RESUME == 1)); then
  DEPLOY_RECEIPT_DIR="$(
    "$TRUSTED_DIRNAME" -- "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT"
  )"
  if [[ "${DEPLOY_RECEIPT_DIR%/*}" != "$CANONICAL_DEPLOY_RECEIPT_ROOT" \
    || ! "${DEPLOY_RECEIPT_DIR##*/}" =~ ^deploy\.[A-Za-z0-9]{8}$ \
    || "${RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT##*/}" \
      != "release-upload-ticket-epoch-rotation.json" \
    || ! -d "$DEPLOY_RECEIPT_DIR" || -L "$DEPLOY_RECEIPT_DIR" \
    || ! -O "$DEPLOY_RECEIPT_DIR" \
    || "$("$TRUSTED_STAT" -c '%a' -- "$DEPLOY_RECEIPT_DIR")" != 700 ]]; then
    echo "epoch-rotation resume receipt is outside its exact private deploy root" >&2
    exit 2
  fi
else
  DEPLOY_RECEIPT_DIR="$(
    "$TRUSTED_MKTEMP" -d -- "$CANONICAL_DEPLOY_RECEIPT_ROOT/deploy.XXXXXXXX"
  )"
  "$TRUSTED_CHMOD" 0700 -- "$DEPLOY_RECEIPT_DIR"
fi
OVERLAY_STAGE_OUTPUT="$DEPLOY_RECEIPT_DIR/overlay-stage.json"
OVERLAY_ACTIVATION_OUTPUT="$DEPLOY_RECEIPT_DIR/overlay-activation.json"
OVERLAY_ROLLBACK_OUTPUT="$DEPLOY_RECEIPT_DIR/overlay-rollback.json"
OVERLAY_ACTIVE_PREFLIGHT_OUTPUT="$DEPLOY_RECEIPT_DIR/active-overlay-preflight.json"
OVERLAY_POSTRECREATE_PREFLIGHT_OUTPUT="$DEPLOY_RECEIPT_DIR/postrecreate-overlay-preflight.json"
PREACTIVATION_COMPOSE_ATTESTATION_OUTPUT="$DEPLOY_RECEIPT_DIR/preactivation-compose-runtime-attestation.json"
DEPLOY_RECOVERY_OUTPUT="$DEPLOY_RECEIPT_DIR/deploy-recovery.json"
PUBLIC_EDGE_HOST_BUILD_ROOT="$DEPLOY_RECEIPT_DIR/host-build"
PLAYWRIGHT_AUTHORITY="$PUBLIC_EDGE_HOST_BUILD_ROOT/playwright-authority.json"
PLAYWRIGHT_AUTHORITY_PREPARATION="$DEPLOY_RECEIPT_DIR/playwright-authority-preparation.json"
if ((RELEASE_UPLOAD_TICKET_EPOCH_ROTATION_RESUME == 0)); then
  RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT="$DEPLOY_RECEIPT_DIR/release-upload-ticket-epoch-rotation.json"
fi
PRECOMPLETION_TRANSACTION_BACKUP="$DEPLOY_RECEIPT_DIR/precompletion-overlay-transaction.json"
STEADY_COMPOSE_ATTESTATION_OUTPUT="$DEPLOY_RECEIPT_DIR/steady-compose-runtime-attestation.json"
COMPOSE_SOURCE_SNAPSHOT="$DEPLOY_RECEIPT_DIR/docker-compose.public-edge.snapshot.yml"
COMPOSE_SOURCE_BINDING_RECEIPT="$DEPLOY_RECEIPT_DIR/compose-source-binding.json"
COMPOSE_ENVIRONMENT_BINDING_RECEIPT="$DEPLOY_RECEIPT_DIR/compose-environment-binding.json"
FINAL_COMPOSE_ATTESTATION_OUTPUT="$COMPOSE_ATTESTATION_OUTPUT"
FINAL_COMPOSE_ATTESTATION_SNAPSHOT="$DEPLOY_RECEIPT_DIR/cutover-final-compose-attestation.json"
PUBLICATION_READINESS_ATTESTATION="$DEPLOY_RECEIPT_DIR/cutover-final-publication-readiness.json"
FINAL_POSTDEPLOY_ATTESTATION_SNAPSHOT="$DEPLOY_RECEIPT_DIR/cutover-final-postdeploy-attestation.json"
FINAL_POSTDEPLOY_ATTESTATION_OUTPUT="$POSTDEPLOY_OUTPUT"
ACTIVE_RUNTIME_AUTHORITY_SNAPSHOT="$DEPLOY_RECEIPT_DIR/cutover-final-active-runtime-authority.json"
CANDIDATE_PROOF_BIND_SOURCE_SNAPSHOT="$DEPLOY_RECEIPT_DIR/candidate-proof-bind-source.json"
PRIOR_PROOF_AUTHORITY_SNAPSHOT="$DEPLOY_RECEIPT_DIR/prior-proof-authority-mount.json"
PRIOR_PROOF_PUBLIC_SNAPSHOT="$DEPLOY_RECEIPT_DIR/prior-proof-public-mount.json"
INSTALL_LINKING_CUTOVER_RECEIPT_ROOT=""
INSTALL_LINKING_REPROOF_ATTEMPT_ID=""
INSTALL_LINKING_POSTQUIESCE_RECEIPT=""
INSTALL_LINKING_POSTQUIESCE_VOLUME_INVENTORY=""
INSTALL_LINKING_PREACTIVATION_VOLUME_INVENTORY=""
INSTALL_LINKING_RUNTIME_AUTHORITY_READINESS=""
INSTALL_LINKING_PRIVATE_POSTDEPLOY_RECEIPT=""
INSTALL_LINKING_PRIVATE_ACTIVE_RUNTIME_RECEIPT=""
INSTALL_LINKING_PUBLIC_ACCEPTANCE_EVIDENCE=""
if ((RECOVERY_ROUTE_REQUESTED == 0)); then
  INSTALL_LINKING_CUTOVER_RECEIPT_ROOT="$(
    "$TRUSTED_DIRNAME" -- "$INSTALL_LINKING_CUTOVER_BOUNDARY"
  )"
  install_linking_deploy_suffix="${DEPLOY_RECEIPT_DIR##*.}"
  if [[ ! "$install_linking_deploy_suffix" =~ ^[A-Za-z0-9]{8}$ ]]; then
    echo "generated InstallLinking deploy receipt suffix is invalid" >&2
    exit 70
  fi
  INSTALL_LINKING_REPROOF_ATTEMPT_ID="deploy-${install_linking_deploy_suffix,,}"
  INSTALL_LINKING_POSTQUIESCE_RECEIPT="$INSTALL_LINKING_CUTOVER_RECEIPT_ROOT/INSTALL_LINKING_POSTGRES_POSTQUIESCE_REPROOF.${INSTALL_LINKING_REPROOF_ATTEMPT_ID}.json"
  INSTALL_LINKING_POSTQUIESCE_VOLUME_INVENTORY="$INSTALL_LINKING_CUTOVER_RECEIPT_ROOT/INSTALL_LINKING_STATE_VOLUME_INVENTORY.post-incumbent-quiesce.${INSTALL_LINKING_REPROOF_ATTEMPT_ID}.json"
  INSTALL_LINKING_PREACTIVATION_VOLUME_INVENTORY="$INSTALL_LINKING_CUTOVER_RECEIPT_ROOT/INSTALL_LINKING_STATE_VOLUME_INVENTORY.pre-overlay-activation.${INSTALL_LINKING_REPROOF_ATTEMPT_ID}.json"
  INSTALL_LINKING_RUNTIME_AUTHORITY_READINESS="$INSTALL_LINKING_CUTOVER_RECEIPT_ROOT/install-linking-authority-readiness-${install_linking_deploy_suffix}.json"
  INSTALL_LINKING_PRIVATE_POSTDEPLOY_RECEIPT="$INSTALL_LINKING_CUTOVER_RECEIPT_ROOT/public-edge-postdeploy-${install_linking_deploy_suffix}.json"
  INSTALL_LINKING_PRIVATE_ACTIVE_RUNTIME_RECEIPT="$INSTALL_LINKING_CUTOVER_RECEIPT_ROOT/active-runtime-${install_linking_deploy_suffix}.json"
  INSTALL_LINKING_PUBLIC_ACCEPTANCE_EVIDENCE="$INSTALL_LINKING_CUTOVER_RECEIPT_ROOT/public-acceptance-${install_linking_deploy_suffix}.json"
fi
CANDIDATE_PORTAL_CONTAINER_NAME="chummer-public-edge-candidate-${DEPLOY_RECEIPT_DIR##*.}"
if [[ ! "$CANDIDATE_PORTAL_CONTAINER_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{7,127}$ ]]; then
  echo "generated public-edge candidate container name is invalid" >&2
  exit 70
fi
CUTOVER_ATTESTOR="$SOURCE_ROOT/scripts/attest_initial_release_shelf_cutover.py"
if [[ ! -f "$CUTOVER_ATTESTOR" || -L "$CUTOVER_ATTESTOR" ]]; then
  echo "audited initial release-shelf cutover attestor is missing or symlinked" >&2
  exit 2
fi
INSTALL_LINKING_CUTOVER_VERIFIER="$ROOT_DIR/scripts/verify_install_linking_cutover_boundary.py"
INSTALL_LINKING_CUTOVER_RUNNER="$SOURCE_ROOT/scripts/run_install_linking_postgres_cutover.py"
INSTALL_LINKING_CUTOVER_MATERIALIZER="$SOURCE_ROOT/scripts/materialize_install_linking_cutover_boundary.py"
if ((RECOVERY_ROUTE_REQUESTED == 0)); then
  for cutover_authority in \
    "$INSTALL_LINKING_CUTOVER_VERIFIER" \
    "$INSTALL_LINKING_CUTOVER_RUNNER" \
    "$INSTALL_LINKING_CUTOVER_MATERIALIZER" \
    "$PLAYWRIGHT_AUTHORITY_PREPARER"; do
    if [[ ! -f "$cutover_authority" || -L "$cutover_authority" \
      || ! -O "$cutover_authority" \
      || "$("$TRUSTED_STAT" -c '%h' -- "$cutover_authority")" != 1 ]]; then
      echo "an audited InstallLinking cutover authority is unsafe" >&2
      exit 2
    fi
    if ! cutover_authority_mode="$("$TRUSTED_STAT" -c '%a' -- "$cutover_authority")" \
      || [[ ! "$cutover_authority_mode" =~ ^[0-7]{3,4}$ ]] \
      || (( (8#$cutover_authority_mode & 8#022) != 0 )); then
      echo "an audited InstallLinking cutover authority is group- or world-writable" >&2
      exit 2
    fi
  done
fi

COMPOSE_SOURCE_ATTESTOR="$SOURCE_ROOT/scripts/attest_public_edge_compose_source.py"
if [[ ! -f "$COMPOSE_SOURCE_ATTESTOR" || -L "$COMPOSE_SOURCE_ATTESTOR" \
  || ! -O "$COMPOSE_SOURCE_ATTESTOR" \
  || "$("$TRUSTED_STAT" -c '%h' -- "$COMPOSE_SOURCE_ATTESTOR")" != 1 ]]; then
  echo "audited public-edge Compose source attestor is unsafe" >&2
  exit 2
fi

if [[ -L "$CANONICAL_DOCKER_CONFIG_ROOT" \
  || (-e "$CANONICAL_DOCKER_CONFIG_ROOT" \
    && (! -d "$CANONICAL_DOCKER_CONFIG_ROOT" || ! -O "$CANONICAL_DOCKER_CONFIG_ROOT")) ]]; then
  echo "canonical public edge Docker configuration root is unsafe" >&2
  exit 2
fi
"$TRUSTED_INSTALL" -d -m 0700 -- \
  "$CANONICAL_DOCKER_CONFIG_ROOT" \
  "$CANONICAL_DOCKER_CONFIG_ROOT/home" \
  "$CANONICAL_DOCKER_CONFIG_ROOT/config"
if [[ -L "$CANONICAL_DOCKER_CONFIG_ROOT/home" \
  || -L "$CANONICAL_DOCKER_CONFIG_ROOT/config" \
  || ! -O "$CANONICAL_DOCKER_CONFIG_ROOT/home" \
  || ! -O "$CANONICAL_DOCKER_CONFIG_ROOT/config" ]]; then
  echo "canonical public edge Docker configuration directories are unsafe" >&2
  exit 2
fi
"$TRUSTED_CHMOD" 0700 -- \
  "$CANONICAL_DOCKER_CONFIG_ROOT" \
  "$CANONICAL_DOCKER_CONFIG_ROOT/home" \
  "$CANONICAL_DOCKER_CONFIG_ROOT/config"

docker_command=(
  "$TRUSTED_ENV" -i
  PATH=/usr/bin:/bin
  HOME="$CANONICAL_DOCKER_CONFIG_ROOT/home"
  DOCKER_CONFIG="$CANONICAL_DOCKER_CONFIG_ROOT/config"
  LANG=C LC_ALL=C
  "$TRUSTED_DOCKER" --context "$CANONICAL_DOCKER_CONTEXT"
)

docker_cli() {
  "${docker_command[@]}" "$@"
}

resolve_exact_image_id() {
  local image_reference="$1"
  local image_id
  image_id="$(docker_cli image inspect "$image_reference" --format '{{.Id}}')" \
    || return 1
  [[ "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || return 1
  printf '%s' "$image_id"
}

compose_command=()
COMPOSE_ATTESTATION_OPERATION=""
configure_compose_operation() {
  local operation="$1"
  local layout_v1_required initial_migration_allowed
  case "$operation" in
    deploy)
      layout_v1_required=true
      initial_migration_allowed=false
      ;;
    initial-release-shelf-cutover)
      layout_v1_required=false
      initial_migration_allowed=true
      ;;
    initial-release-shelf-cutover-recover)
      layout_v1_required=false
      initial_migration_allowed=false
      ;;
    *)
      echo "public edge Compose operation is not an audited literal" >&2
      return 2
      ;;
  esac
  COMPOSE_ATTESTATION_OPERATION="$operation"
  compose_command=(
    "$TRUSTED_ENV" -i
    PATH=/usr/bin:/bin
    HOME="$CANONICAL_DOCKER_CONFIG_ROOT/home"
    DOCKER_CONFIG="$CANONICAL_DOCKER_CONFIG_ROOT/config"
    LANG=C LC_ALL=C
    CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT="$BUILD_CONTEXT"
    CHUMMER_RUN_SERVICES_CONTEXT_DIR="$SOURCE_ROOT"
    CHUMMER_RUN_SERVICES_SOURCE="$SOURCE_ROOT"
    CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR="$OVERLAY_ROOT"
    CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT="$PROJECTION_SNAPSHOT_ROOT"
    CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE="$RUNTIME_PROOF_BIND_SOURCE"
    CHUMMER_PUBLIC_EDGE_PORT="$PUBLIC_EDGE_PORT"
    ASPNETCORE_ENVIRONMENT=Production
    CHUMMER_PUBLIC_ALLOWED_HOSTS=chummer.run
    CHUMMER_PUBLIC_CANONICAL_ORIGIN="$CANONICAL_BASE_URL"
    CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED="$layout_v1_required"
    CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED="$initial_migration_allowed"
    "$TRUSTED_DOCKER" --context "$CANONICAL_DOCKER_CONTEXT" compose
    --env-file "$ENV_FILE" -p "$COMPOSE_PROJECT"
    -f "$COMPOSE_SOURCE_SNAPSHOT" --project-directory "$SOURCE_ROOT"
  )
}

if ((INITIAL_RELEASE_SHELF_CUTOVER == 1)); then
  configure_compose_operation initial-release-shelf-cutover
elif ((INITIAL_RELEASE_SHELF_CUTOVER_RECOVERY == 1)); then
  configure_compose_operation initial-release-shelf-cutover-recover
else
  configure_compose_operation deploy
fi

compose_cli() {
  run_compose_source_guarded "${compose_command[@]}" "$@"
}

trusted_source_python() {
  "$TRUSTED_ENV" -i \
    PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
    CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT="$BUILD_CONTEXT" \
    CHUMMER_RUN_SERVICES_CONTEXT_DIR="$SOURCE_ROOT" \
    CHUMMER_RUN_SERVICES_SOURCE="$SOURCE_ROOT" \
    CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR="$OVERLAY_ROOT" \
    CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT="$PROJECTION_SNAPSHOT_ROOT" \
    CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE="$RUNTIME_PROOF_BIND_SOURCE" \
    CHUMMER_PUBLIC_EDGE_PORT="$PUBLIC_EDGE_PORT" \
    "$TRUSTED_PYTHON" -I "$@"
}

capture_release_upload_ticket_epoch_history_sha256() {
  local history_metadata
  local history_sha256
  if [[ -f "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
    && ! -L "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
    && -O "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" ]]; then
    history_metadata="$(
      "$TRUSTED_STAT" -c '%a|%h' -- \
        "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY"
    )" || return 1
    [[ "$history_metadata" == '600|1' ]] || return 1
    history_sha256="$(
      "$TRUSTED_SHA256SUM" -- \
        "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY"
    )" || return 1
    history_sha256="${history_sha256%% *}"
    [[ "$history_sha256" =~ ^[0-9a-f]{64}$ ]] || return 1
    printf '%s\n' "$history_sha256"
    return 0
  fi
  if [[ ! -e "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
    && ! -L "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
    && "$RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_EXPECTED_SHA256" == absent ]]; then
    printf '%s\n' absent
    return 0
  fi
  return 1
}

capture_release_upload_ticket_epoch_bootstrap_marker_sha256() {
  local marker_metadata
  local marker_sha256
  if [[ -f "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" \
    && ! -L "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" \
    && -O "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" ]]; then
    marker_metadata="$(
      "$TRUSTED_STAT" -c '%a|%h' -- \
        "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER"
    )" || return 1
    [[ "$marker_metadata" == '600|1' ]] || return 1
    marker_sha256="$(
      "$TRUSTED_SHA256SUM" -- \
        "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER"
    )" || return 1
    marker_sha256="${marker_sha256%% *}"
    [[ "$marker_sha256" =~ ^[0-9a-f]{64}$ ]] || return 1
    printf '%s\n' "$marker_sha256"
    return 0
  fi
  if [[ ! -e "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" \
    && ! -L "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" \
    && "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_EXPECTED_SHA256" \
      == absent ]]; then
    printf '%s\n' absent
    return 0
  fi
  return 1
}

if ((RELEASE_UPLOAD_TICKET_EPOCH_ROTATION_RESUME == 1)); then
  if ! trusted_source_python "$COMPOSE_SOURCE_ATTESTOR" verify \
    --source "$COMPOSE_FILE" \
    --snapshot "$COMPOSE_SOURCE_SNAPSHOT" \
    --receipt "$COMPOSE_SOURCE_BINDING_RECEIPT" >/dev/null; then
    echo "epoch-rotation resume Compose authority is not the original immutable snapshot" >&2
    exit 76
  fi
  resume_receipt_sha256="$(
    "$TRUSTED_SHA256SUM" -- "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT"
  )"
  resume_receipt_sha256="${resume_receipt_sha256%% *}"
  if [[ "$resume_receipt_sha256" \
    != "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_EXPECTED_SHA256" ]]; then
    echo "epoch-rotation resume receipt does not match its external pin" >&2
    exit 76
  fi
  epoch_rotation_status=0
  printf '%s\n' "$deploy_lock_owner_token" \
    | trusted_source_python \
      "$SOURCE_ROOT/scripts/rotate_release_upload_ticket_epoch.py" \
      --env-file "$ENV_FILE" \
      --active-runtime-authority "$CANONICAL_ACTIVE_RUNTIME_AUTHORITY" \
      --epoch-authority-output \
        "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_AUTHORITY" \
      --epoch-history-path \
        "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
      --expected-epoch-history-sha256 \
        "$RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_EXPECTED_SHA256" \
      --epoch-history-bootstrap-authority \
        "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_AUTHORITY_INPUT" \
      --expected-epoch-history-bootstrap-authority-sha256 \
        "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_AUTHORITY_SHA256" \
      --epoch-history-bootstrap-marker \
        "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" \
      --expected-epoch-history-bootstrap-marker-sha256 \
        "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_EXPECTED_SHA256" \
      --edge-waf-local-evidence-source \
        "$RELEASE_UPLOAD_TICKET_EDGE_WAF_LOCAL_EVIDENCE_SOURCE_INPUT" \
      --expected-edge-waf-local-evidence-sha256 \
        "$RELEASE_UPLOAD_TICKET_EDGE_WAF_LOCAL_EVIDENCE_SOURCE_SHA256" \
      --output "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" \
      --expected-existing-receipt-sha256 \
        "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_EXPECTED_SHA256" \
      --expected-env-sha256-before \
        "$RELEASE_UPLOAD_TICKET_ENV_SHA256_BEFORE" \
      --expected-image-id "$RELEASE_UPLOAD_TICKET_EXPECTED_IMAGE_ID" \
      --expected-proof-sha256 \
        "$RELEASE_UPLOAD_TICKET_PROOF_BIND_SOURCE_SHA256" \
      --image-tag "$IMAGE_TAG" \
      --expected-source-head "${EXPECTED_HEAD,,}" \
      --new-epoch "$RELEASE_UPLOAD_TICKET_NEXT_EPOCH" \
      --expected-portal-replicas 1 \
      --shared-mutation-lock-fd 0 \
      --docker-config-root "$CANONICAL_DOCKER_CONFIG_ROOT" \
      --docker-context "$CANONICAL_DOCKER_CONTEXT" \
      --compose-file "$COMPOSE_SOURCE_SNAPSHOT" \
      --project-name "$COMPOSE_PROJECT" \
      --source-root "$SOURCE_ROOT" \
      --build-context "$BUILD_CONTEXT" \
      --overlay-root "$OVERLAY_ROOT" \
      --projection-root "$PROJECTION_SNAPSHOT_ROOT" \
      --proof-bind-source "$RUNTIME_PROOF_BIND_SOURCE" \
      --published-port "$PUBLIC_EDGE_PORT" \
      --base-url "$BASE_URL" \
      --old-ticket-path "$RELEASE_UPLOAD_OLD_TICKET_PATH" \
      --old-ticket-authority-fd 3 \
      3<"$RELEASE_UPLOAD_OLD_TICKET_AUTHORITY_INPUT" \
      >/dev/null || epoch_rotation_status=$?
  RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_OBSERVED_SHA256="$(
    capture_release_upload_ticket_epoch_history_sha256
  )" || exit 76
  RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_OBSERVED_SHA256="$(
    capture_release_upload_ticket_epoch_bootstrap_marker_sha256
  )" || exit 76
  RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256="$(
    "$TRUSTED_SHA256SUM" -- "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT"
  )" || exit 76
  RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256="${RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256%% *}"
  if [[ ! "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256" \
    =~ ^[0-9a-f]{64}$ ]]; then
    exit 76
  fi
  if ((epoch_rotation_status == 75)); then
    epoch_rotation_fail_forward_required=0
    if ! release_deploy_lock; then
      echo "precommit epoch rotation refusal but failed to release its authenticated mutation lock" >&2
      exit 70
    fi
    trap - EXIT HUP INT TERM
    printf \
      'release_upload_ticket_epoch_refused_before_commit receipt=%s receipt_sha256=%s history=%s history_sha256=%s bootstrap_marker=%s bootstrap_marker_sha256=%s\n' \
      "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" \
      "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256" \
      "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
      "$RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_OBSERVED_SHA256" \
      "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" \
      "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_OBSERVED_SHA256" >&2
    exit 75
  fi
  if ((epoch_rotation_status != 0)); then
    printf \
      'release_upload_ticket_epoch_resume_incomplete receipt=%s receipt_sha256=%s history=%s history_sha256=%s bootstrap_marker=%s bootstrap_marker_sha256=%s\n' \
      "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" \
      "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256" \
      "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
      "$RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_OBSERVED_SHA256" \
      "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" \
      "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_OBSERVED_SHA256" >&2
    exit "$epoch_rotation_status"
  fi
  epoch_rotation_fail_forward_required=0
  if ! release_deploy_lock; then
    echo "completed epoch rotation but failed to release its authenticated mutation lock" >&2
    exit 70
  fi
  trap - EXIT HUP INT TERM
  printf \
    'release_upload_ticket_epoch_rotated receipt=%s receipt_sha256=%s history=%s history_sha256=%s\n' \
    "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" \
    "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256" \
    "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
    "$RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_OBSERVED_SHA256"
  exit 0
fi

if ! trusted_source_python "$COMPOSE_SOURCE_ATTESTOR" capture \
  --source "$COMPOSE_FILE" \
  --snapshot "$COMPOSE_SOURCE_SNAPSHOT" \
  --receipt "$COMPOSE_SOURCE_BINDING_RECEIPT" >/dev/null; then
  echo "failed to capture the immutable public-edge Compose source" >&2
  exit 2
fi
if ! trusted_source_python "$COMPOSE_SOURCE_ATTESTOR" capture-environment \
  --source "$ENV_FILE" \
  --receipt "$COMPOSE_ENVIRONMENT_BINDING_RECEIPT" >/dev/null; then
  echo "failed to bind the owner-only public-edge Compose environment" >&2
  exit 2
fi

verify_compose_source_binding() {
  trusted_source_python "$COMPOSE_SOURCE_ATTESTOR" verify \
    --source "$COMPOSE_FILE" \
    --snapshot "$COMPOSE_SOURCE_SNAPSHOT" \
    --receipt "$COMPOSE_SOURCE_BINDING_RECEIPT" >/dev/null
}

verify_compose_environment_binding() {
  trusted_source_python "$COMPOSE_SOURCE_ATTESTOR" verify-environment \
    --source "$ENV_FILE" \
    --receipt "$COMPOSE_ENVIRONMENT_BINDING_RECEIPT" >/dev/null
}

run_compose_source_guarded() {
  local command_status=0
  if ! verify_compose_source_binding \
    || ! verify_compose_environment_binding; then
    echo "public-edge Compose source or environment changed before a guarded read" >&2
    return 2
  fi
  "$@" || command_status=$?
  if ! verify_compose_source_binding \
    || ! verify_compose_environment_binding; then
    echo "public-edge Compose source or environment changed during a guarded read" >&2
    return 2
  fi
  return "$command_status"
}

run_compose_source_only_guarded() {
  local command_status=0
  if ! verify_compose_source_binding; then
    echo "public-edge Compose source changed before recovery" >&2
    return 2
  fi
  "$@" || command_status=$?
  if ! verify_compose_source_binding; then
    echo "public-edge Compose source changed during recovery" >&2
    return 2
  fi
  return "$command_status"
}

if ! cutover_state_json="$(
  trusted_source_python "$CUTOVER_ATTESTOR" inspect-deploy-state \
    --shelf-root "$CANONICAL_RELEASE_SHELF_ROOT" \
    --state-root "$CUTOVER_STATE_ROOT" \
    --source-head "${EXPECTED_HEAD,,}"
)"; then
  echo "initial release-shelf cutover state is malformed or unstable" >&2
  exit 2
fi
if ! CUTOVER_STATE_CLASSIFICATION="$(
  printf '%s' "$cutover_state_json" \
    | trusted_source_python -c '
import json, sys

def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SystemExit(1)
        result[key] = value
    return result

payload = json.load(sys.stdin, object_pairs_hook=reject_duplicates)
classification = payload.get("classification")
if (
    set(payload) != {"contractName", "status", "classification"}
    or payload.get("contractName")
    != "chummer.initial-release-shelf-cutover-deploy-state/v1"
    or payload.get("status") != "pass"
    or classification
    not in {
        "absent", "prestate-resumable", "unknown-outcome", "aborted",
        "steady-handoff", "complete",
    }
):
    raise SystemExit(1)
print(classification, end="")
'
)"; then
  echo "initial release-shelf cutover state classification is invalid" >&2
  exit 2
fi
case "$DEPLOY_OPERATION" in
  initial-release-shelf-cutover)
    if [[ "$CUTOVER_STATE_CLASSIFICATION" != absent \
      && "$CUTOVER_STATE_CLASSIFICATION" != prestate-resumable ]]; then
      echo "initial release-shelf cutover state is not an exact resumable prestate" >&2
      exit 2
    fi
    ;;
  deploy|release-upload-ticket-epoch-rotate)
    if [[ "$CUTOVER_STATE_CLASSIFICATION" == steady-handoff ]]; then
      CUTOVER_STEADY_HANDOFF=1
    elif [[ "$CUTOVER_STATE_CLASSIFICATION" == unknown-outcome ]]; then
      echo "initial release-shelf cutover outcome is unknown; run recover before deploy" >&2
      exit 2
    fi
    ;;
  recover)
    if [[ "$CUTOVER_STATE_CLASSIFICATION" == unknown-outcome ]]; then
      CUTOVER_RECOVERY_REEXEC=1
    fi
    ;;
  initial-release-shelf-cutover-recover)
    if [[ "$CUTOVER_STATE_CLASSIFICATION" != unknown-outcome ]]; then
      echo "initial release-shelf recovery requires one unresolved candidate-start receipt" >&2
      exit 2
    fi
    ;;
esac
CUTOVER_FINALIZE_REQUIRED=0
if ((INITIAL_RELEASE_SHELF_CUTOVER == 1 \
  || INITIAL_RELEASE_SHELF_CUTOVER_RECOVERY == 1 \
  || CUTOVER_STEADY_HANDOFF == 1)); then
  CUTOVER_FINALIZE_REQUIRED=1
fi

container_proof_sha256_by_id() {
  local container_id="$1"
  local proof_path="$2"
  local rendered digest
  rendered="$(
    docker_cli container exec "$container_id" \
      /usr/bin/sha256sum -- "$proof_path"
  )" || return 1
  digest="${rendered%% *}"
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  [[ "$rendered" == "$digest  $proof_path" ]] || return 1
  printf '%s' "$digest"
}

snapshot_container_proof_by_id() {
  local container_id="$1"
  local proof_path="$2"
  local output_path="$3"
  local expected_sha256="$4"
  [[ "$expected_sha256" =~ ^[0-9a-f]{64}$ ]] || return 1
  docker_cli container exec "$container_id" /usr/bin/cat -- "$proof_path" \
    | trusted_source_python -c '
# chummer_snapshot_container_proof_v1
import hashlib, os, pathlib, re, stat, sys, tempfile

output = pathlib.Path(sys.argv[1])
expected_sha256 = sys.argv[2]
maximum_bytes = 16 * 1024 * 1024
if not output.is_absolute() or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
    raise SystemExit(1)
for candidate in (output.parent,):
    current = pathlib.Path(candidate.anchor)
    for component in candidate.parts[1:]:
        current /= component
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise SystemExit(1)
parent_metadata = output.parent.lstat()
if (
    not stat.S_ISDIR(parent_metadata.st_mode)
    or parent_metadata.st_uid != os.getuid()
    or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    or output.exists()
    or output.is_symlink()
):
    raise SystemExit(1)
payload = sys.stdin.buffer.read(maximum_bytes + 1)
if len(payload) > maximum_bytes or hashlib.sha256(payload).hexdigest() != expected_sha256:
    raise SystemExit(1)
descriptor, temporary_name = tempfile.mkstemp(
    prefix=f".{output.name}.",
    suffix=".tmp",
    dir=output.parent,
)
temporary = pathlib.Path(temporary_name)
try:
    os.fchmod(descriptor, 0o600)
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short proof snapshot write")
        view = view[written:]
    os.fsync(descriptor)
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or metadata.st_size != len(payload)
    ):
        raise SystemExit(1)
finally:
    os.close(descriptor)
try:
    os.link(temporary, output, follow_symlinks=False)
finally:
    temporary.unlink(missing_ok=True)
installed = output.lstat()
if (
    not stat.S_ISREG(installed.st_mode)
    or stat.S_IMODE(installed.st_mode) != 0o600
    or installed.st_uid != os.getuid()
    or installed.st_nlink != 1
    or installed.st_size != len(payload)
    or hashlib.sha256(output.read_bytes()).hexdigest() != expected_sha256
):
    raise SystemExit(1)
' "$output_path" "$expected_sha256"
}

resolve_active_runtime_authority() {
  if [[ ! -e "$CANONICAL_ACTIVE_RUNTIME_AUTHORITY" \
    && ! -L "$CANONICAL_ACTIVE_RUNTIME_AUTHORITY" ]]; then
    printf 'unmanaged|0||||0||'
    return 0
  fi
  trusted_source_python -c '
import hashlib, json, os, re, stat, sys
from datetime import datetime
from pathlib import Path

def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result

def read_private_json(path, *, maximum):
    if not path.is_absolute():
        raise ValueError("private receipt path is not absolute")
    current = Path(path.anchor)
    for component in path.parent.parts[1:]:
        current /= component
        if stat.S_ISLNK(current.lstat().st_mode):
            raise ValueError("private receipt has a symlinked parent")
    parent = path.parent.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        raise ValueError("private receipt parent is unsafe")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size < 1
            or before.st_size > maximum
        ):
            raise ValueError("private receipt metadata is unsafe")
        raw = os.read(descriptor, before.st_size + 1)
        after = os.fstat(descriptor)
        if (
            len(raw) != before.st_size
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
        ):
            raise ValueError("private receipt changed while open")
    finally:
        os.close(descriptor)
    return (
        json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates),
        hashlib.sha256(raw).hexdigest(),
    )

path = Path(sys.argv[1])
flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
try:
    descriptor = os.open(path, flags)
except OSError:
    raise SystemExit(1)
try:
    before = os.fstat(descriptor)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) & 0o077
    ):
        raise SystemExit(1)
    with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as handle:
        payload = json.load(handle, object_pairs_hook=reject_duplicates)
    after = os.fstat(descriptor)
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise SystemExit(1)
finally:
    os.close(descriptor)
portal = payload.get("portal") or {}
legacy_keys = {"contractName", "status", "generatedAtUtc", "portal"}
enriched_keys = legacy_keys | {
    "installLinkingAuthorityReadinessPath",
    "installLinkingAuthorityReadinessSha256",
}
if (
    frozenset(payload) not in {frozenset(legacy_keys), frozenset(enriched_keys)}
    or payload.get("contractName") != "chummer.public-edge.active-runtime-authority/v1"
    or payload.get("status") != "pass"
    or not isinstance(payload.get("generatedAtUtc"), str)
    or set(portal) != {
        "existed", "containerId", "containerName", "imageId", "wasRunning",
        "proofAuthorityMountSha256", "proofPublicMountSha256",
    }
    or not isinstance(portal.get("existed"), bool)
    or not isinstance(portal.get("wasRunning"), bool)
):
    raise SystemExit(1)
try:
    generated = datetime.fromisoformat(payload["generatedAtUtc"])
except ValueError:
    raise SystemExit(1)
if generated.tzinfo is None:
    raise SystemExit(1)
if set(payload) == enriched_keys:
    readiness_path = Path(
        str(payload.get("installLinkingAuthorityReadinessPath") or "")
    )
    readiness_expected_sha256 = str(
        payload.get("installLinkingAuthorityReadinessSha256") or ""
    )
    try:
        readiness, readiness_sha256 = read_private_json(
            readiness_path,
            maximum=4096,
        )
        readiness_checked = datetime.fromisoformat(
            str(readiness.get("checkedAtUtc") or "").replace("Z", "+00:00")
        )
    except (OSError, UnicodeError, ValueError):
        raise SystemExit(1)
    if (
        re.fullmatch(
            r"install-linking-authority-readiness-[A-Za-z0-9]{8}\.json",
            readiness_path.name,
        )
        is None
        or re.fullmatch(r"[0-9a-f]{64}", readiness_expected_sha256) is None
        or readiness_sha256 != readiness_expected_sha256
        or set(readiness)
        != {
            "authorityIdentitySha256",
            "checkedAtUtc",
            "code",
            "contractName",
            "currentRoleMatches",
            "leastPrivilegeValid",
            "ready",
            "runtimeRoleSha256",
            "status",
        }
        or readiness.get("contractName")
        != "chummer.install_linking_postgres_runtime_authority_readiness.v1"
        or readiness.get("status") != "pass"
        or readiness.get("ready") is not True
        or readiness.get("code") != "runtime_role_least_privilege"
        or readiness.get("currentRoleMatches") is not True
        or readiness.get("leastPrivilegeValid") is not True
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(readiness.get("authorityIdentitySha256") or ""),
        )
        is None
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(readiness.get("runtimeRoleSha256") or ""),
        )
        is None
        or readiness_checked.tzinfo is None
        or readiness_checked.utcoffset().total_seconds() != 0
    ):
        raise SystemExit(1)
existed = portal["existed"]
container_id = str(portal.get("containerId") or "")
container_name = str(portal.get("containerName") or "")
image_id = str(portal.get("imageId") or "")
authority_digest = str(portal.get("proofAuthorityMountSha256") or "")
public_digest = str(portal.get("proofPublicMountSha256") or "")
if existed:
    if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
        raise SystemExit(1)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", container_name) is None:
        raise SystemExit(1)
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
        raise SystemExit(1)
    if portal["wasRunning"]:
        if (
            re.fullmatch(r"[0-9a-f]{64}", authority_digest) is None
            or public_digest != authority_digest
        ):
            raise SystemExit(1)
    elif authority_digest or public_digest:
        raise SystemExit(1)
elif any(
    (container_id, container_name, image_id, authority_digest, public_digest)
) or portal["wasRunning"]:
    raise SystemExit(1)
print(
    "|".join(
        (
            "managed",
            "1" if existed else "0",
            container_id,
            container_name,
            image_id,
            "1" if portal["wasRunning"] else "0",
            authority_digest,
            public_digest,
        )
    ),
    end="",
)
' "$CANONICAL_ACTIVE_RUNTIME_AUTHORITY"
}

run_deploy_recovery() {
  local baseline_adoption_args=()
  if ((RECOVERY_BASELINE_ADOPTION == 1)); then
    baseline_adoption_args+=(--adopt-verified-prior-runtime-baseline)
  fi
  # Recovery resolves existing containers by immutable Docker labels and never
  # interpolates the mutable environment file, so it remains available after an
  # environment-binding failure.
  run_compose_source_only_guarded \
    trusted_source_python "$SOURCE_ROOT/scripts/public_edge_deploy_recovery.py" \
    --source-root "$SOURCE_ROOT" \
    --active-root "$OVERLAY_ROOT" \
    --backup-root "$OVERLAY_BACKUP_ROOT" \
    --snapshot "$OVERLAY_PRIOR_STATE_OUTPUT" \
    --activation-receipt "$OVERLAY_ACTIVATION_OUTPUT" \
    --overlay-rollback-output "$OVERLAY_ROLLBACK_OUTPUT" \
    --output "$DEPLOY_RECOVERY_OUTPUT" \
    --runtime-authority-output "$CANONICAL_ACTIVE_RUNTIME_AUTHORITY" \
    --shared-mutation-lock-token "$deploy_lock_owner_token" \
    --docker-config-root "$CANONICAL_DOCKER_CONFIG_ROOT" \
    --docker-context "$CANONICAL_DOCKER_CONTEXT" \
    --compose-file "$COMPOSE_SOURCE_SNAPSHOT" \
    --env-file "$ENV_FILE" \
    --project-name "$COMPOSE_PROJECT" \
    --build-context "$BUILD_CONTEXT" \
    --public-projection-snapshot-root "$PROJECTION_SNAPSHOT_ROOT" \
    --published-port "$PUBLIC_EDGE_PORT" \
    --portal-image-tag "$IMAGE_TAG" \
    --tool-image-tag "$TOOL_IMAGE_TAG" \
    "${baseline_adoption_args[@]}"
}

docker_context_identity="$(docker_cli context inspect "$CANONICAL_DOCKER_CONTEXT" \
  --format '{{.Name}}|{{.Endpoints.docker.Host}}|{{.Endpoints.docker.SkipTLSVerify}}')"
if [[ "$docker_context_identity" != "$CANONICAL_DOCKER_CONTEXT|$CANONICAL_DOCKER_HOST|false" ]]; then
  echo "public edge deploy refuses a non-canonical Docker daemon context" >&2
  exit 2
fi

# Recovery is an explicit idempotent command and also the only route taken when
# a prior durable journal exists. A normal deploy performs reconciliation and
# exits; it never silently treats interrupted state as a new deployment base.
if ((RECOVERY_ROUTE_REQUESTED == 1)); then
  if ! run_deploy_recovery; then
    release_deploy_lock || true
    trap - EXIT HUP INT TERM
    exit 70
  fi
  if ! release_deploy_lock; then
    trap - EXIT HUP INT TERM
    exit 70
  fi
  trap - EXIT HUP INT TERM
  if ((CUTOVER_RECOVERY_REEXEC == 1)); then
    echo "public_edge_deploy_runtime_recovery_complete; entering release-shelf recovery-only posture"
    exec "$SCRIPT_PATH" initial-release-shelf-cutover-recover
  fi
  if [[ "$DEPLOY_OPERATION" == deploy \
    || "$DEPLOY_OPERATION" == release-upload-ticket-epoch-rotate ]]; then
    echo "public_edge_deploy_recovered_interrupted_transaction; rerun the requested deployment operation explicitly"
  else
    if [[ "$CUTOVER_STATE_CLASSIFICATION" == steady-handoff ]]; then
      echo "initial_release_shelf_cutover_committed_safe_handoff; run deploy for canonical true/false steady state"
      exit 0
    fi
    echo "public_edge_deploy_recovery_complete"
  fi
  exit 0
fi

INSTALL_LINKING_CUTOVER_ID=""
verify_install_linking_cutover_boundary() {
  local expected_boundary_sha256="$1"
  local expected_phase="$2"
  local observed_portal_image_id="$3"
  local observed_tool_image_id="$4"
  local expected_cutover_args=()
  if [[ -n "$INSTALL_LINKING_CUTOVER_ID" ]]; then
    expected_cutover_args=(
      --expected-cutover-id "$INSTALL_LINKING_CUTOVER_ID"
    )
  fi
  trusted_source_python "$INSTALL_LINKING_CUTOVER_VERIFIER" \
    --boundary "$INSTALL_LINKING_CUTOVER_BOUNDARY" \
    --expected-boundary-sha256 "$expected_boundary_sha256" \
    "${expected_cutover_args[@]}" \
    --expected-source-head "${EXPECTED_HEAD,,}" \
    --expected-candidate-image-id \
      "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
    --expected-candidate-tool-image-id \
      "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
    --observed-candidate-image-id "$observed_portal_image_id" \
    --observed-candidate-tool-image-id "$observed_tool_image_id" \
    --source-root "$SOURCE_ROOT" \
    --env-file "$ENV_FILE" \
    --expected-phase "$expected_phase"
}

if ! install_linking_boundary_verification="$(
  verify_install_linking_cutover_boundary \
    "$INSTALL_LINKING_CUTOVER_BOUNDARY_SHA256" \
    validate_completed \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID"
)"; then
  echo "InstallLinking cutover boundary verification failed before Docker mutation" >&2
  exit 2
fi
if ! install_linking_boundary_binding="$(
  printf '%s' "$install_linking_boundary_verification" \
    | trusted_source_python -c '
# InstallLinking verified boundary binding parser.
import json, re, sys

def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result

payload = json.load(sys.stdin, object_pairs_hook=reject_duplicates)
expected_keys = {
    "activeBuildInfoPath", "activeBuildInfoSha256", "boundaryReceiptPath",
    "boundaryReceiptSha256", "candidateImageId", "candidatePortalTag",
    "candidateToolImageId", "candidateToolTag",
    "canonicalPortalTagIdBeforeAndAfter",
    "canonicalToolTagIdBeforeAndAfter", "composeSha256", "contractName",
    "cutoverId", "envSha256", "finalRunReceiptPath",
    "finalRunReceiptSha256", "finalRunReceiptStatus", "phase",
    "runnerSha256", "sourceHead", "status",
}
hex64 = re.compile(r"[0-9a-f]{64}")
image = re.compile(r"sha256:[0-9a-f]{64}")
path_fields = (
    "activeBuildInfoPath", "boundaryReceiptPath", "finalRunReceiptPath",
)
if (
    set(payload) != expected_keys
    or payload.get("contractName")
    != "chummer.install_linking_postgres_cutover_boundary_verification.v1"
    or payload.get("status") != "pass"
    or payload.get("phase") != "validate_completed"
    or payload.get("finalRunReceiptStatus") != "pass"
    or any(
        hex64.fullmatch(str(payload.get(field) or "")) is None
        for field in (
            "activeBuildInfoSha256", "boundaryReceiptSha256",
            "composeSha256", "envSha256", "finalRunReceiptSha256",
            "runnerSha256",
        )
    )
    or image.fullmatch(str(payload.get("candidateImageId") or "")) is None
    or image.fullmatch(str(payload.get("candidateToolImageId") or "")) is None
    or any(
        not isinstance(payload.get(field), str)
        or not payload[field].startswith("/")
        or "|" in payload[field]
        or "\n" in payload[field]
        for field in path_fields
    )
):
    raise SystemExit(1)
portal_prior = payload.get("canonicalPortalTagIdBeforeAndAfter")
tool_prior = payload.get("canonicalToolTagIdBeforeAndAfter")
if any(value is not None and image.fullmatch(str(value)) is None for value in (portal_prior, tool_prior)):
    raise SystemExit(1)
values = (
    payload["cutoverId"], payload["candidatePortalTag"],
    payload["candidateToolTag"], payload["activeBuildInfoPath"],
    payload["activeBuildInfoSha256"], payload["composeSha256"],
    payload["envSha256"], payload["runnerSha256"],
    "" if portal_prior is None else portal_prior,
    "" if tool_prior is None else tool_prior,
)
if any("|" in str(value) or "\n" in str(value) for value in values):
    raise SystemExit(1)
print("|".join(str(value) for value in values), end="")
'
)"; then
  echo "InstallLinking verified boundary binding is malformed" >&2
  exit 2
fi
IFS='|' read -r verified_cutover_id INSTALL_LINKING_CANDIDATE_PORTAL_TAG \
  INSTALL_LINKING_CANDIDATE_TOOL_TAG INSTALL_LINKING_ACTIVE_BUILD_INFO \
  INSTALL_LINKING_ACTIVE_BUILD_INFO_SHA256 INSTALL_LINKING_COMPOSE_SHA256 \
  INSTALL_LINKING_ENV_SHA256 INSTALL_LINKING_RUNNER_SHA256 \
  INSTALL_LINKING_PRIOR_PORTAL_TAG_ID INSTALL_LINKING_PRIOR_TOOL_TAG_ID \
  <<<"$install_linking_boundary_binding"
INSTALL_LINKING_CUTOVER_ID="$verified_cutover_id"
if [[ ! "$INSTALL_LINKING_CUTOVER_ID" \
    =~ ^[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}$ \
  || ! "$INSTALL_LINKING_CANDIDATE_PORTAL_TAG" \
    =~ ^chummer-run-api:cutover-[0-9a-f]{24}$ \
  || ! "$INSTALL_LINKING_CANDIDATE_TOOL_TAG" \
    =~ ^chummer-install-linking-postgres-tool:cutover-[0-9a-f]{24}$ ]]; then
  echo "InstallLinking verified candidate tag binding is invalid" >&2
  exit 2
fi
if ! install_linking_build_source_provenance="$(
  trusted_source_python -c '
# InstallLinking candidate build-source provenance parser.
import pathlib, re, sys
scripts = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(scripts))
from materialize_install_linking_cutover_boundary import (
    bind_exact_build_source_replay,
    bind_active_build_info,
    select_exact_build_context_provenance,
)

path, digest, payload = bind_active_build_info(
    pathlib.Path(sys.argv[2]),
    cutover_id=sys.argv[3],
    candidate_image_id=sys.argv[4],
    candidate_tool_image_id=sys.argv[5],
)
if str(path) != sys.argv[2] or digest != sys.argv[6]:
    raise SystemExit(1)
provenance = payload.get("buildSourceProvenance")
if not isinstance(provenance, dict):
    raise SystemExit(1)
_build_context_name, build_context = (
    select_exact_build_context_provenance(provenance)
)
replay = bind_exact_build_source_replay(
    provenance,
    synthetic_workspace_root=sys.argv[7] or None,
    build_context_root=sys.argv[8] or None,
    run_services_root=sys.argv[9] or None,
    hub_registry_root=sys.argv[10] or None,
    design_product_root=sys.argv[11] or None,
    fleet_media_factory_root=sys.argv[12] or None,
)
source_roots = replay["sourceRoots"]
content_sha256 = replay["contentSha256"]
values = (
    (provenance.get("hub-registry") or {}).get("head"),
    (provenance.get("design-product") or {}).get("head"),
    (provenance.get("fleet-media-factory-contracts") or {}).get("head"),
    build_context.get("dockerignoreSha256"),
    replay["buildContextName"],
    replay["syntheticWorkspaceRoot"] or "-",
    replay["buildContextRoot"] or "-",
    source_roots["run-services-source"] or "-",
    source_roots["hub-registry"] or "-",
    source_roots["design-product"] or "-",
    source_roots["fleet-media-factory-contracts"] or "-",
    content_sha256["run-services-source"] or "-",
    content_sha256["hub-registry"] or "-",
    content_sha256["design-product"] or "-",
    content_sha256["fleet-media-factory-contracts"] or "-",
)
if (
    any(not isinstance(value, str) or "|" in value or "\n" in value for value in values)
    or any(re.fullmatch(r"[0-9a-f]{40}", value) is None for value in values[:3])
    or re.fullmatch(r"[0-9a-f]{64}", values[3]) is None
):
    raise SystemExit(1)
print("|".join(values), end="")
' "$SOURCE_ROOT/scripts" "$INSTALL_LINKING_ACTIVE_BUILD_INFO" \
    "$INSTALL_LINKING_CUTOVER_ID" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
    "$INSTALL_LINKING_ACTIVE_BUILD_INFO_SHA256" \
    "$INSTALL_LINKING_REPLAY_SYNTHETIC_WORKSPACE_ROOT" \
    "$INSTALL_LINKING_REPLAY_BUILD_CONTEXT_ROOT" \
    "$INSTALL_LINKING_REPLAY_RUN_SERVICES_ROOT" \
    "$INSTALL_LINKING_REPLAY_HUB_REGISTRY_ROOT" \
    "$INSTALL_LINKING_REPLAY_DESIGN_PRODUCT_ROOT" \
    "$INSTALL_LINKING_REPLAY_FLEET_MEDIA_FACTORY_ROOT"
)"; then
  echo "InstallLinking candidate build-source provenance is invalid" >&2
  exit 2
fi
IFS='|' read -r INSTALL_LINKING_EXPECTED_HUB_REGISTRY_HEAD \
  INSTALL_LINKING_EXPECTED_DESIGN_PRODUCT_HEAD \
  INSTALL_LINKING_EXPECTED_FLEET_MEDIA_FACTORY_HEAD \
  INSTALL_LINKING_EXPECTED_BUILD_CONTEXT_DOCKERIGNORE_SHA256 \
  INSTALL_LINKING_BUILD_CONTEXT_NAME \
  INSTALL_LINKING_REPLAY_SYNTHETIC_WORKSPACE_ROOT \
  INSTALL_LINKING_REPLAY_BUILD_CONTEXT_ROOT \
  INSTALL_LINKING_REPLAY_RUN_SERVICES_ROOT \
  INSTALL_LINKING_REPLAY_HUB_REGISTRY_ROOT \
  INSTALL_LINKING_REPLAY_DESIGN_PRODUCT_ROOT \
  INSTALL_LINKING_REPLAY_FLEET_MEDIA_FACTORY_ROOT \
  INSTALL_LINKING_EXPECTED_RUN_SERVICES_CONTENT_SHA256 \
  INSTALL_LINKING_EXPECTED_HUB_REGISTRY_CONTENT_SHA256 \
  INSTALL_LINKING_EXPECTED_DESIGN_PRODUCT_CONTENT_SHA256 \
  INSTALL_LINKING_EXPECTED_FLEET_MEDIA_FACTORY_CONTENT_SHA256 \
  <<<"$install_linking_build_source_provenance"
INSTALL_LINKING_POSTQUIESCE_SOURCE_ROOT="$SOURCE_ROOT"
install_linking_source_replay_args=()
case "$INSTALL_LINKING_BUILD_CONTEXT_NAME" in
  canonical-build-context)
    for canonical_sentinel in \
      "$INSTALL_LINKING_REPLAY_SYNTHETIC_WORKSPACE_ROOT" \
      "$INSTALL_LINKING_REPLAY_BUILD_CONTEXT_ROOT" \
      "$INSTALL_LINKING_REPLAY_RUN_SERVICES_ROOT" \
      "$INSTALL_LINKING_REPLAY_HUB_REGISTRY_ROOT" \
      "$INSTALL_LINKING_REPLAY_DESIGN_PRODUCT_ROOT" \
      "$INSTALL_LINKING_REPLAY_FLEET_MEDIA_FACTORY_ROOT" \
      "$INSTALL_LINKING_EXPECTED_RUN_SERVICES_CONTENT_SHA256" \
      "$INSTALL_LINKING_EXPECTED_HUB_REGISTRY_CONTENT_SHA256" \
      "$INSTALL_LINKING_EXPECTED_DESIGN_PRODUCT_CONTENT_SHA256" \
      "$INSTALL_LINKING_EXPECTED_FLEET_MEDIA_FACTORY_CONTENT_SHA256"; do
      if [[ "$canonical_sentinel" != "-" ]]; then
        echo "canonical InstallLinking provenance contains synthetic replay inputs" >&2
        exit 2
      fi
    done
    ;;
  synthetic-build-context)
    if [[ ! "$INSTALL_LINKING_EXPECTED_RUN_SERVICES_CONTENT_SHA256" \
        =~ ^[0-9a-f]{64}$ \
      || ! "$INSTALL_LINKING_EXPECTED_HUB_REGISTRY_CONTENT_SHA256" \
        =~ ^[0-9a-f]{64}$ \
      || ! "$INSTALL_LINKING_EXPECTED_DESIGN_PRODUCT_CONTENT_SHA256" \
        =~ ^[0-9a-f]{64}$ \
      || ! "$INSTALL_LINKING_EXPECTED_FLEET_MEDIA_FACTORY_CONTENT_SHA256" \
        =~ ^[0-9a-f]{64}$ ]]; then
      echo "synthetic InstallLinking content replay pins are invalid" >&2
      exit 2
    fi
    INSTALL_LINKING_POSTQUIESCE_SOURCE_ROOT="$INSTALL_LINKING_REPLAY_RUN_SERVICES_ROOT"
    install_linking_source_replay_args=(
      --synthetic-workspace-root
      "$INSTALL_LINKING_REPLAY_SYNTHETIC_WORKSPACE_ROOT"
      --build-context-root "$INSTALL_LINKING_REPLAY_BUILD_CONTEXT_ROOT"
      --hub-registry-root "$INSTALL_LINKING_REPLAY_HUB_REGISTRY_ROOT"
      --design-product-root "$INSTALL_LINKING_REPLAY_DESIGN_PRODUCT_ROOT"
      --fleet-media-factory-root
      "$INSTALL_LINKING_REPLAY_FLEET_MEDIA_FACTORY_ROOT"
      --expected-run-services-content-sha256
      "$INSTALL_LINKING_EXPECTED_RUN_SERVICES_CONTENT_SHA256"
      --expected-hub-registry-content-sha256
      "$INSTALL_LINKING_EXPECTED_HUB_REGISTRY_CONTENT_SHA256"
      --expected-design-product-content-sha256
      "$INSTALL_LINKING_EXPECTED_DESIGN_PRODUCT_CONTENT_SHA256"
      --expected-fleet-media-factory-content-sha256
      "$INSTALL_LINKING_EXPECTED_FLEET_MEDIA_FACTORY_CONTENT_SHA256"
    )
    ;;
  *)
    echo "InstallLinking build-context replay kind is invalid" >&2
    exit 2
    ;;
esac
if ! trusted_source_python "$INSTALL_LINKING_CUTOVER_RUNNER" \
  --source-replay-preflight \
  --source-root "$INSTALL_LINKING_POSTQUIESCE_SOURCE_ROOT" \
  "${install_linking_source_replay_args[@]}" \
  --expected-head "${EXPECTED_HEAD,,}" \
  --expected-compose-sha256 "$INSTALL_LINKING_COMPOSE_SHA256" \
  --env-file "$ENV_FILE" \
  --expected-env-sha256 "$INSTALL_LINKING_ENV_SHA256" \
  --expected-runner-sha256 "$INSTALL_LINKING_RUNNER_SHA256" \
  --expected-hub-registry-head \
    "$INSTALL_LINKING_EXPECTED_HUB_REGISTRY_HEAD" \
  --expected-design-product-head \
    "$INSTALL_LINKING_EXPECTED_DESIGN_PRODUCT_HEAD" \
  --expected-fleet-media-factory-head \
    "$INSTALL_LINKING_EXPECTED_FLEET_MEDIA_FACTORY_HEAD" \
  --expected-build-context-dockerignore-sha256 \
    "$INSTALL_LINKING_EXPECTED_BUILD_CONTEXT_DOCKERIGNORE_SHA256" \
  --cutover-id "$INSTALL_LINKING_CUTOVER_ID" \
  --receipt-root "$INSTALL_LINKING_CUTOVER_RECEIPT_ROOT" \
  --boundary-output "$INSTALL_LINKING_CUTOVER_BOUNDARY" \
  --expected-candidate-image-id \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
  --expected-candidate-tool-image-id \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
  --active-build-info "$INSTALL_LINKING_ACTIVE_BUILD_INFO" \
  --expected-active-build-info-sha256 \
    "$INSTALL_LINKING_ACTIVE_BUILD_INFO_SHA256" \
  >/dev/null; then
  echo "InstallLinking candidate build-source replay preflight failed" >&2
  exit 2
fi
if ! builder_identity="$(
  docker_cli buildx ls --format json \
    | "$TRUSTED_PYTHON" -I -c '
import json, sys
matches = []
for raw in sys.stdin:
    if not raw.strip():
        continue
    item = json.loads(raw)
    if item.get("Name") == "default":
        matches.append(item)
if len(matches) != 1:
    raise SystemExit(1)
item = matches[0]
nodes = item.get("Nodes")
if (
    item.get("Current") is not True
    or item.get("Driver") != "docker"
    or not isinstance(nodes, list)
    or len(nodes) != 1
    or nodes[0].get("Name") != "default"
    or nodes[0].get("Endpoint") != "default"
    or nodes[0].get("Status") != "running"
):
    raise SystemExit(1)
print("default|docker|default|running")
'
)" || [[ "$builder_identity" != "default|docker|default|running" ]]; then
  echo "public edge deploy refuses a non-canonical Buildx builder" >&2
  exit 2
fi

# Run every source/Compose gate before verified staging or the image build can
# mutate candidate state. Compose interpolation is intentionally checked here so
# missing certificate, PostgreSQL, and release-shelf posture inputs cannot fail
# only after the build or portal quiesce.
source_gate_args=(
  --repo-root "$SOURCE_ROOT"
  --expected-head "$EXPECTED_HEAD"
  --compose-file "$COMPOSE_FILE"
  --compose-service chummer-portal
  --require-upstream
)

if [[ "${CHUMMER_PUBLIC_EDGE_IGNORE_GENERATED_PROOF_DRIFT:-0}" =~ ^(1|true|TRUE|yes|YES|on|ON)$ ]]; then
  source_gate_args+=(--ignore-generated-proof-drift)
fi

run_compose_source_guarded \
  trusted_source_python "$ROOT_DIR/scripts/verify_public_edge_deploy_source.py" \
    "${source_gate_args[@]}"
# Combined-branch test requirement: proof hardening must provide both receipt flags
# and runtimeProofBindSource.sha256 before this deployment command is executable.
trusted_source_python "$SOURCE_ROOT/scripts/check_public_edge_deploy_preflight.py" \
  --source-root "$SOURCE_ROOT" \
  --skip-overlay-marker-check \
  --public-projection-snapshot-root "$PROJECTION_SNAPSHOT_ROOT" \
  --public-projection-purpose code-deploy \
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256" \
  --runtime-proof-bind-source-sha256 "$RUNTIME_PROOF_BIND_SOURCE_SHA256"
compose_cli --profile install-linking-postgres-admin config --format json \
  | trusted_source_python "$SOURCE_ROOT/scripts/validate_public_edge_compose_runtime.py" \
      --operation "$COMPOSE_ATTESTATION_OPERATION" \
      --project-name "$COMPOSE_PROJECT" \
      --source-root "$SOURCE_ROOT" \
      --build-context "$BUILD_CONTEXT" \
      --overlay-root "$OVERLAY_ROOT" \
      --projection-root "$PROJECTION_SNAPSHOT_ROOT" \
      --runtime-proof-bind-source "$RUNTIME_PROOF_BIND_SOURCE" \
      --published-port "$PUBLIC_EDGE_PORT" \
      --output "$COMPOSE_ATTESTATION_OUTPUT"
if ! observed_install_linking_candidate_image_id="$(
  resolve_exact_image_id "$INSTALL_LINKING_CANDIDATE_PORTAL_TAG"
)" \
  || ! observed_install_linking_candidate_tool_image_id="$(
    resolve_exact_image_id "$INSTALL_LINKING_CANDIDATE_TOOL_TAG"
  )"; then
  echo "InstallLinking unique candidate images are unavailable" >&2
  exit 2
fi
if [[ "$observed_install_linking_candidate_image_id" \
    != "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
  || "$observed_install_linking_candidate_tool_image_id" \
    != "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" ]]; then
  echo "InstallLinking unique candidate image identity differs from its independent pin" >&2
  exit 2
fi
if ! verified_install_linking_boundary_verification="$(
  verify_install_linking_cutover_boundary \
    "$INSTALL_LINKING_CUTOVER_BOUNDARY_SHA256" \
    validate_completed \
    "$observed_install_linking_candidate_image_id" \
    "$observed_install_linking_candidate_tool_image_id"
)" \
  || [[ "$verified_install_linking_boundary_verification" \
    != "$install_linking_boundary_verification" ]]; then
  echo "InstallLinking cutover boundary or candidate images changed during verification" >&2
  exit 2
fi
if ((CUTOVER_STEADY_HANDOFF == 1)); then
  if ! trusted_source_python "$CUTOVER_ATTESTOR" snapshot-evidence \
    --kind compose \
    --source "$COMPOSE_ATTESTATION_OUTPUT" \
    --output "$FINAL_COMPOSE_ATTESTATION_SNAPSHOT" >/dev/null; then
    echo "failed to snapshot the final steady Compose attestation" >&2
    exit 2
  fi
fi

if ((INITIAL_RELEASE_SHELF_CUTOVER == 1)); then
  trusted_source_python "$CUTOVER_ATTESTOR" prepare \
    --shelf-root "$CANONICAL_RELEASE_SHELF_ROOT" \
    --state-root "$CUTOVER_STATE_ROOT" \
    --source-head "${EXPECTED_HEAD,,}" >/dev/null
elif ((INITIAL_RELEASE_SHELF_CUTOVER_RECOVERY == 1)); then
  if [[ ! -d "$CUTOVER_STATE_ROOT" || -L "$CUTOVER_STATE_ROOT" \
    || ! -O "$CUTOVER_STATE_ROOT" ]]; then
    echo "initial release-shelf recovery state root is unsafe" >&2
    exit 2
  fi
fi

# Materialize and locally verify the replacement bind-mounted payload before either
# the image tag or live runtime is touched. The independent release-receipt digest
# binds both this staging pass and the later reuse-only activation pass.
"$TRUSTED_INSTALL" -d -m 0700 -- "$PUBLIC_EDGE_HOST_BUILD_ROOT"
trusted_source_python "$PLAYWRIGHT_AUTHORITY_PREPARER" \
  --host-build-root "$PUBLIC_EDGE_HOST_BUILD_ROOT" \
  --output "$PLAYWRIGHT_AUTHORITY_PREPARATION"
if [[ ! -f "$PLAYWRIGHT_AUTHORITY" || -L "$PLAYWRIGHT_AUTHORITY" \
  || ! -O "$PLAYWRIGHT_AUTHORITY" \
  || "$("$TRUSTED_STAT" -c '%h' -- "$PLAYWRIGHT_AUTHORITY")" != 1 ]]; then
  echo "operation-private Playwright authority is unsafe" >&2
  exit 2
fi
PLAYWRIGHT_AUTHORITY_SHA256="$(
  "$TRUSTED_SHA256SUM" -- "$PLAYWRIGHT_AUTHORITY"
)"
PLAYWRIGHT_AUTHORITY_SHA256="${PLAYWRIGHT_AUTHORITY_SHA256%% *}"
if [[ ! "$PLAYWRIGHT_AUTHORITY_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "operation-private Playwright authority digest is malformed" >&2
  exit 70
fi
trusted_source_python "$SOURCE_ROOT/scripts/publish_public_edge_portal_overlay.py" \
  --source-root "$SOURCE_ROOT" \
  --active-root "$OVERLAY_ROOT" \
  --staging-root "$OVERLAY_STAGING_ROOT" \
  --backup-root "$OVERLAY_BACKUP_ROOT" \
  --build-root "$OVERLAY_BUILD_ROOT" \
  --host-build-root "$PUBLIC_EDGE_HOST_BUILD_ROOT" \
  --downloads-source-root "$CANONICAL_RELEASE_SHELF_ROOT" \
  --playwright-authority "$PLAYWRIGHT_AUTHORITY" \
  --playwright-authority-sha256 "$PLAYWRIGHT_AUTHORITY_SHA256" \
  --surface-profile public-download \
  --delivery-phase windows-preview \
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256" \
  --output "$OVERLAY_STAGE_OUTPUT"

if [[ ! -f "$RUNTIME_PROOF_BIND_SOURCE" \
  || -L "$RUNTIME_PROOF_BIND_SOURCE" \
  || ! -O "$RUNTIME_PROOF_BIND_SOURCE" ]]; then
  echo "authenticated CURRENT runtime proof bind source is unsafe" >&2
  exit 2
fi
runtime_proof_bind_source_sha256="$(
  "$TRUSTED_SHA256SUM" -- "$RUNTIME_PROOF_BIND_SOURCE"
)"
runtime_proof_bind_source_sha256="${runtime_proof_bind_source_sha256%% *}"
if [[ "$runtime_proof_bind_source_sha256" != "$RUNTIME_PROOF_BIND_SOURCE_SHA256" ]]; then
  echo "authenticated CURRENT runtime proof changed after preflight" >&2
  exit 2
fi
"$TRUSTED_INSTALL" -m 0600 -- \
  "$RUNTIME_PROOF_BIND_SOURCE" \
  "$CANDIDATE_PROOF_BIND_SOURCE_SNAPSHOT"

resolve_image_tag_id() {
  local resolved_ids
  if ! resolved_ids="$(docker_cli image ls --quiet --no-trunc --filter "reference=$1")"; then
    return 1
  fi
  # shellcheck disable=SC2016  # $0 is intentionally evaluated by awk.
  resolved_ids="$(printf '%s\n' "$resolved_ids" | "$TRUSTED_AWK" 'NF && !seen[$0]++')"
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

mark_deploy_phase() {
  trusted_source_python "$SOURCE_ROOT/scripts/public_edge_overlay_transaction.py" mark-phase \
    --source-root "$SOURCE_ROOT" \
    --active-root "$OVERLAY_ROOT" \
    --output "$OVERLAY_PRIOR_STATE_OUTPUT" \
    --phase "$1" \
    --shared-mutation-lock-token "$deploy_lock_owner_token"
}

candidate_portal_container_id=""

abort_portal_recreate() {
  local failure_label="$1"
  local failure_status="$2"
  printf 'public-edge portal %s failed; invoking durable reconciliation\n' "$failure_label" >&2
  exit "$failure_status"
}

retain_unknown_postquiesce_authority() {
  local failure_label="$1"
  retain_deploy_authority_on_exit=1
  printf \
    'public-edge portal %s is unknown; retaining mutation lock and durable transaction authority\n' \
    "$failure_label" >&2
  exit 70
}

classify_install_linking_postquiesce_attempt() {
  trusted_source_python -c '
# InstallLinking post-quiesce attempt receipt classifier.
import pathlib, re, sys

scripts = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(scripts))
from materialize_install_linking_cutover_boundary import (
    bind_active_build_info,
    classify_postquiesce_reproof,
)

(
    build_path,
    build_sha256,
    build_info,
) = bind_active_build_info(
    pathlib.Path(sys.argv[3]),
    cutover_id=sys.argv[4],
    candidate_image_id=sys.argv[5],
    candidate_tool_image_id=sys.argv[6],
)
if str(build_path) != sys.argv[3] or build_sha256 != sys.argv[7]:
    raise SystemExit(1)
classification, receipt_sha256, _ = classify_postquiesce_reproof(
    pathlib.Path(sys.argv[2]),
    boundary_output=pathlib.Path(sys.argv[8]),
    cutover_id=sys.argv[4],
    candidate_image_id=sys.argv[5],
    candidate_tool_image_id=sys.argv[6],
    candidate_build_info_sha256=build_sha256,
    candidate_build_info=build_info,
    expected_mutation_lock_token_sha256=sys.argv[9],
    expected_volume_inventory_sha256=sys.argv[10],
)
if (
    classification not in {"pass", "safe_fail", "unknown"}
    or re.fullmatch(r"[0-9a-f]{64}", receipt_sha256) is None
):
    raise SystemExit(1)
print(f"{classification}|{receipt_sha256}", end="")
' "$SOURCE_ROOT/scripts" "$INSTALL_LINKING_POSTQUIESCE_RECEIPT" \
    "$INSTALL_LINKING_ACTIVE_BUILD_INFO" "$INSTALL_LINKING_CUTOVER_ID" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
    "$INSTALL_LINKING_ACTIVE_BUILD_INFO_SHA256" \
    "$INSTALL_LINKING_CUTOVER_BOUNDARY" "$deploy_lock_token_digest" \
    "$INSTALL_LINKING_POSTQUIESCE_VOLUME_INVENTORY_SHA256"
}

bind_install_linking_postquiesce_runtime_authority_identity() {
  trusted_source_python -c '
# InstallLinking post-quiesce runtime authority identity parser.
import pathlib, re, sys

scripts = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(scripts))
from materialize_install_linking_cutover_boundary import (
    POSTQUIESCE_REPROOF_PHASE,
    bind_active_build_info,
    bind_phase_evidence,
    bind_postquiesce_reproof,
)

build_path, build_sha256, build_info = bind_active_build_info(
    pathlib.Path(sys.argv[3]),
    cutover_id=sys.argv[4],
    candidate_image_id=sys.argv[5],
    candidate_tool_image_id=sys.argv[6],
)
if str(build_path) != sys.argv[3] or build_sha256 != sys.argv[7]:
    raise SystemExit(1)
_, _, receipt = bind_postquiesce_reproof(
    pathlib.Path(sys.argv[2]),
    boundary_output=pathlib.Path(sys.argv[8]),
    cutover_id=sys.argv[4],
    candidate_image_id=sys.argv[5],
    candidate_tool_image_id=sys.argv[6],
    candidate_build_info_sha256=build_sha256,
    candidate_build_info=build_info,
    expected_volume_inventory_sha256=sys.argv[9],
)
_, _, evidence = bind_phase_evidence(
    pathlib.Path(str(receipt["phaseEvidencePath"])),
    phase=POSTQUIESCE_REPROOF_PHASE,
    cutover_id=sys.argv[4],
    candidate_image_id=sys.argv[5],
    candidate_tool_image_id=sys.argv[6],
    candidate_build_info_sha256=build_sha256,
    candidate_build_info=build_info,
    boundary_output=pathlib.Path(sys.argv[8]),
    postquiesce_attempt_id=str(receipt["attemptId"]),
)
values = (
    evidence.get("authorityIdentitySha256"),
    evidence.get("runtimeRoleSha256"),
)
if any(
    not isinstance(value, str)
    or re.fullmatch(r"[0-9a-f]{64}", value) is None
    for value in values
):
    raise SystemExit(1)
print("|".join(values), end="")
' "$SOURCE_ROOT/scripts" "$INSTALL_LINKING_POSTQUIESCE_RECEIPT" \
    "$INSTALL_LINKING_ACTIVE_BUILD_INFO" "$INSTALL_LINKING_CUTOVER_ID" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
    "$INSTALL_LINKING_ACTIVE_BUILD_INFO_SHA256" \
    "$INSTALL_LINKING_CUTOVER_BOUNDARY" \
    "$INSTALL_LINKING_POSTQUIESCE_VOLUME_INVENTORY_SHA256"
}

publish_private_snapshot() {
  local source_path="$1"
  local output_path="$2"
  local encoding="$3"
  local require_source_mode_0600="$4"
  trusted_source_python -c '
# Public-edge private snapshot publisher.
import hashlib, json, os, pathlib, stat, sys, tempfile

source = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
encoding = sys.argv[3]
require_mode_0600 = sys.argv[4] == "1"
if (
    not source.is_absolute()
    or not output.is_absolute()
    or source == output
    or encoding not in {"raw", "canonical-json"}
):
    raise SystemExit(1)
for candidate in (source, output.parent):
    current = pathlib.Path(candidate.anchor)
    for component in candidate.parts[1:]:
        current /= component
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise SystemExit(1)
source_metadata = source.lstat()
if (
    not stat.S_ISREG(source_metadata.st_mode)
    or source_metadata.st_nlink != 1
    or source_metadata.st_uid != os.getuid()
    or source_metadata.st_size <= 0
    or source_metadata.st_size > 16 * 1024 * 1024
    or (require_mode_0600 and stat.S_IMODE(source_metadata.st_mode) != 0o600)
    or ((not require_mode_0600) and stat.S_IMODE(source_metadata.st_mode) & 0o022)
):
    raise SystemExit(1)
parent_metadata = output.parent.lstat()
if (
    not stat.S_ISDIR(parent_metadata.st_mode)
    or parent_metadata.st_uid != os.getuid()
    or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    or output.exists()
    or output.is_symlink()
):
    raise SystemExit(1)
flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(source, flags)
try:
    before = os.fstat(descriptor)
    raw = bytearray()
    while True:
        chunk = os.read(descriptor, 65536)
        if not chunk:
            break
        raw.extend(chunk)
        if len(raw) > 16 * 1024 * 1024:
            raise SystemExit(1)
    after = os.fstat(descriptor)
finally:
    os.close(descriptor)
source_after = source.lstat()
identity = (
    before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
    before.st_ctime_ns, before.st_nlink, stat.S_IMODE(before.st_mode),
)
if identity != (
    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
    after.st_ctime_ns, after.st_nlink, stat.S_IMODE(after.st_mode),
) or identity != (
    source_after.st_dev, source_after.st_ino, source_after.st_size,
    source_after.st_mtime_ns, source_after.st_ctime_ns,
    source_after.st_nlink, stat.S_IMODE(source_after.st_mode),
) or len(raw) != before.st_size:
    raise SystemExit(1)
payload = bytes(raw)
if encoding == "canonical-json":
    def reject_duplicates(pairs):
        parsed = {}
        for key, value in pairs:
            if key in parsed:
                raise ValueError("duplicate")
            parsed[key] = value
        return parsed
    def reject_constant(_value):
        raise ValueError("non-finite")
    parsed = json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
    )
    if not isinstance(parsed, dict):
        raise SystemExit(1)
    payload = (
        json.dumps(parsed, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
temporary_descriptor, temporary_name = tempfile.mkstemp(
    prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
)
temporary = pathlib.Path(temporary_name)
try:
    os.fchmod(temporary_descriptor, 0o600)
    written = 0
    while written < len(payload):
        written += os.write(temporary_descriptor, payload[written:])
    os.fsync(temporary_descriptor)
finally:
    os.close(temporary_descriptor)
try:
    os.link(temporary, output, follow_symlinks=False)
finally:
    temporary.unlink(missing_ok=True)
output_metadata = output.lstat()
if (
    not stat.S_ISREG(output_metadata.st_mode)
    or output_metadata.st_nlink != 1
    or output_metadata.st_uid != os.getuid()
    or stat.S_IMODE(output_metadata.st_mode) != 0o600
):
    raise SystemExit(1)
parent_descriptor = os.open(
    output.parent,
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
)
try:
    os.fsync(parent_descriptor)
finally:
    os.close(parent_descriptor)
print(hashlib.sha256(payload).hexdigest(), end="")
' "$source_path" "$output_path" "$encoding" "$require_source_mode_0600"
}

stable_private_receipt_sha256() {
  local receipt_path="$1"
  trusted_source_python -c '
# InstallLinking stable private receipt hasher.
import hashlib, os, pathlib, stat, sys

path = pathlib.Path(sys.argv[1])
if not path.is_absolute():
    raise SystemExit(1)
current = pathlib.Path(path.anchor)
for component in path.parts[1:]:
    current /= component
    metadata = current.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise SystemExit(1)
metadata = path.lstat()
parent_metadata = path.parent.lstat()
if (
    not stat.S_ISREG(metadata.st_mode)
    or metadata.st_nlink != 1
    or metadata.st_uid != os.getuid()
    or stat.S_IMODE(metadata.st_mode) != 0o600
    or metadata.st_size <= 0
    or metadata.st_size > 16 * 1024 * 1024
    or not stat.S_ISDIR(parent_metadata.st_mode)
    or parent_metadata.st_uid != os.getuid()
    or stat.S_IMODE(parent_metadata.st_mode) != 0o700
):
    raise SystemExit(1)
descriptor = os.open(
    path,
    os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
)
try:
    before = os.fstat(descriptor)
    payload = bytearray()
    while True:
        chunk = os.read(descriptor, 65536)
        if not chunk:
            break
        payload.extend(chunk)
        if len(payload) > 16 * 1024 * 1024:
            raise SystemExit(1)
    after = os.fstat(descriptor)
finally:
    os.close(descriptor)
final_metadata = path.lstat()
identity = (
    before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
    before.st_ctime_ns, before.st_nlink, stat.S_IMODE(before.st_mode),
)
if (
    identity
    != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
        after.st_ctime_ns, after.st_nlink, stat.S_IMODE(after.st_mode),
    )
    or identity
    != (
        final_metadata.st_dev, final_metadata.st_ino, final_metadata.st_size,
        final_metadata.st_mtime_ns, final_metadata.st_ctime_ns,
        final_metadata.st_nlink, stat.S_IMODE(final_metadata.st_mode),
    )
    or len(payload) != before.st_size
):
    raise SystemExit(1)
print(hashlib.sha256(payload).hexdigest(), end="")
' "$receipt_path"
}

verify_install_linking_public_acceptance_boundary() {
  local boundary_sha256 boundary_verification
  boundary_sha256="$(
    stable_private_receipt_sha256 "$INSTALL_LINKING_CUTOVER_BOUNDARY"
  )" || return 1
  [[ "$boundary_sha256" =~ ^[0-9a-f]{64}$ ]] || return 1
  boundary_verification="$(
    verify_install_linking_cutover_boundary \
      "$boundary_sha256" \
      public_acceptance_completed \
      "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
      "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID"
  )" || return 1
  if ! printf '%s' "$boundary_verification" \
    | trusted_source_python -c '
# InstallLinking accepted boundary closure parser.
import json, sys

def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result

payload = json.load(sys.stdin, object_pairs_hook=reject_duplicates)
expected_keys = {
    "activeBuildInfoPath", "activeBuildInfoSha256", "boundaryReceiptPath",
    "boundaryReceiptSha256", "candidateImageId", "candidatePortalTag",
    "candidateToolImageId", "candidateToolTag",
    "canonicalPortalTagIdBeforeAndAfter",
    "canonicalToolTagIdBeforeAndAfter", "composeSha256", "contractName",
    "cutoverId", "envSha256", "finalRunReceiptPath",
    "finalRunReceiptSha256", "finalRunReceiptStatus", "phase",
    "runnerSha256", "sourceHead", "status",
}
if (
    set(payload) != expected_keys
    or payload.get("contractName")
    != "chummer.install_linking_postgres_cutover_boundary_verification.v1"
    or payload.get("status") != "pass"
    or payload.get("phase") != "public_acceptance_completed"
    or payload.get("finalRunReceiptStatus") != "pass"
    or payload.get("boundaryReceiptSha256") != sys.argv[1]
    or payload.get("cutoverId") != sys.argv[2]
    or payload.get("candidateImageId") != sys.argv[3]
    or payload.get("candidateToolImageId") != sys.argv[4]
    or payload.get("activeBuildInfoSha256") != sys.argv[5]
):
    raise SystemExit(1)
' "$boundary_sha256" \
      "$INSTALL_LINKING_CUTOVER_ID" \
      "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
      "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
      "$INSTALL_LINKING_ACTIVE_BUILD_INFO_SHA256"; then
    return 1
  fi
  printf '%s' "$boundary_sha256"
}

write_install_linking_public_acceptance_evidence() {
  trusted_source_python -c '
# InstallLinking public acceptance evidence publisher.
import hashlib, json, os, pathlib, re, stat, sys, tempfile

(
    output_value,
    cutover_id,
    candidate_image_id,
    candidate_tool_image_id,
    build_info_sha256,
    postdeploy_path_value,
    postdeploy_sha256,
    active_runtime_path_value,
    active_runtime_sha256,
    postquiesce_path_value,
    postquiesce_sha256,
) = sys.argv[1:]
output = pathlib.Path(output_value)
paths = tuple(
    pathlib.Path(value)
    for value in (
        postdeploy_path_value,
        active_runtime_path_value,
        postquiesce_path_value,
    )
)
if (
    not output.is_absolute()
    or any(not path.is_absolute() or path.parent != output.parent for path in paths)
    or len(set(paths)) != 3
    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}", cutover_id) is None
    or re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_image_id) is None
    or re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_tool_image_id) is None
    or any(
        re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in (
            build_info_sha256,
            postdeploy_sha256,
            active_runtime_sha256,
            postquiesce_sha256,
        )
    )
):
    raise SystemExit(1)
current = pathlib.Path(output.anchor)
for component in output.parent.parts[1:]:
    current /= component
    metadata = current.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise SystemExit(1)
parent_metadata = output.parent.lstat()
if (
    not stat.S_ISDIR(parent_metadata.st_mode)
    or parent_metadata.st_uid != os.getuid()
    or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    or output.exists()
    or output.is_symlink()
):
    raise SystemExit(1)
payload = {
    "activeRuntimeAuthorityPath": active_runtime_path_value,
    "activeRuntimeAuthoritySha256": active_runtime_sha256,
    "candidateBuildInfoSha256": build_info_sha256,
    "candidateContainerImageId": candidate_image_id,
    "candidateImageId": candidate_image_id,
    "candidateToolImageId": candidate_tool_image_id,
    "contractName": (
        "chummer.install_linking_postgres_public_acceptance_evidence.v1"
    ),
    "cutoverId": cutover_id,
    "overlayAccepted": True,
    "postQuiesceReceiptPath": postquiesce_path_value,
    "postQuiesceReceiptSha256": postquiesce_sha256,
    "postdeployReceiptPath": postdeploy_path_value,
    "postdeployReceiptSha256": postdeploy_sha256,
    "publicReadinessAccepted": True,
    "status": "pass",
}
encoded = (
    json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
).encode("utf-8")
descriptor, temporary_name = tempfile.mkstemp(
    prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
)
temporary = pathlib.Path(temporary_name)
try:
    os.fchmod(descriptor, 0o600)
    written = 0
    while written < len(encoded):
        written += os.write(descriptor, encoded[written:])
    os.fsync(descriptor)
finally:
    os.close(descriptor)
try:
    os.link(temporary, output, follow_symlinks=False)
finally:
    temporary.unlink(missing_ok=True)
metadata = output.lstat()
if (
    not stat.S_ISREG(metadata.st_mode)
    or metadata.st_nlink != 1
    or metadata.st_uid != os.getuid()
    or stat.S_IMODE(metadata.st_mode) != 0o600
):
    raise SystemExit(1)
parent_descriptor = os.open(
    output.parent,
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
)
try:
    os.fsync(parent_descriptor)
finally:
    os.close(parent_descriptor)
print(hashlib.sha256(encoded).hexdigest(), end="")
' "$INSTALL_LINKING_PUBLIC_ACCEPTANCE_EVIDENCE" \
    "$INSTALL_LINKING_CUTOVER_ID" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
    "$INSTALL_LINKING_ACTIVE_BUILD_INFO_SHA256" \
    "$INSTALL_LINKING_PRIVATE_POSTDEPLOY_RECEIPT" \
    "$INSTALL_LINKING_PRIVATE_POSTDEPLOY_RECEIPT_SHA256" \
    "$INSTALL_LINKING_PRIVATE_ACTIVE_RUNTIME_RECEIPT" \
    "$INSTALL_LINKING_PRIVATE_ACTIVE_RUNTIME_RECEIPT_SHA256" \
    "$INSTALL_LINKING_POSTQUIESCE_RECEIPT" \
    "$INSTALL_LINKING_POSTQUIESCE_RECEIPT_SHA256"
}

INSTALL_LINKING_STATE_VOLUME_INSPECT_FORMAT='{{json .Id}} {{json .Name}} {{json .Image}} {{json .State.Running}} {{json .Config.Labels}} {{json .Mounts}}'

list_install_linking_state_volume_consumer_ids() {
  local raw_ids
  raw_ids="$(
    docker_cli container ls --all --quiet --no-trunc \
      --filter "volume=$CANONICAL_INSTALL_LINKING_STATE_VOLUME"
  )" || return 1
  printf '%s' "$raw_ids" | trusted_source_python -c '
# InstallLinking state-volume consumer ID parser.
import re, sys

raw = sys.stdin.read()
identifiers = raw.splitlines()
if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in identifiers):
    raise SystemExit(1)
if len(identifiers) != len(set(identifiers)):
    raise SystemExit(1)
print("\n".join(sorted(identifiers)), end="")
'
}

capture_install_linking_state_volume_consumers_once() {
  local identifiers container_id raw_record parsed_record
  identifiers="$(list_install_linking_state_volume_consumer_ids)" || return 1
  while IFS= read -r container_id; do
    [[ -n "$container_id" ]] || continue
    raw_record="$(
      docker_cli container inspect \
        --format "$INSTALL_LINKING_STATE_VOLUME_INSPECT_FORMAT" \
        "$container_id"
    )" || return 1
    parsed_record="$(
      printf '%s' "$raw_record" | trusted_source_python -c '
# InstallLinking state-volume consumer parser.
import hashlib, json, re, sys

decoder = json.JSONDecoder()
raw = sys.stdin.read()
values = []
position = 0
while position < len(raw):
    while position < len(raw) and raw[position].isspace():
        position += 1
    if position == len(raw):
        break
    value, position = decoder.raw_decode(raw, position)
    values.append(value)
if len(values) != 6:
    raise SystemExit(1)
container_id, name, image_id, running, labels, mounts = values
expected_id = sys.argv[1]
volume_name = sys.argv[2]
cutover_id = sys.argv[3]
incumbent_id = sys.argv[4]
incumbent_name = sys.argv[5]
incumbent_image_id = sys.argv[6]
candidate_tool_image_id = sys.argv[7]
if (
    container_id != expected_id
    or re.fullmatch(r"[0-9a-f]{64}", str(container_id or "")) is None
    or not isinstance(name, str)
    or re.fullmatch(r"/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name) is None
    or re.fullmatch(r"sha256:[0-9a-f]{64}", str(image_id or "")) is None
    or type(running) is not bool
    or not isinstance(labels, dict)
    or not isinstance(mounts, list)
):
    raise SystemExit(1)
matching_mounts = [
    mount
    for mount in mounts
    if isinstance(mount, dict)
    and mount.get("Type") == "volume"
    and mount.get("Name") == volume_name
]
if len(matching_mounts) != 1:
    raise SystemExit(1)
mount = matching_mounts[0]
if (
    mount.get("Destination") != "/app/state"
    or type(mount.get("RW")) is not bool
):
    raise SystemExit(1)
container_name = name[1:]
project = labels.get("com.docker.compose.project")
service = labels.get("com.docker.compose.service")
oneoff = labels.get("com.docker.compose.oneoff")
classification = ""
job_name = None
if container_id == incumbent_id:
    if (
        not incumbent_id
        or container_name != incumbent_name
        or image_id != incumbent_image_id
        or running is not False
        or mount["RW"] is not True
        or project != "chummer6-hub"
        or service != "chummer-portal"
        or oneoff != "False"
    ):
        raise SystemExit(1)
    classification = "incumbent_portal"
else:
    suffix = hashlib.sha256(cutover_id.encode("utf-8")).hexdigest()[:24]
    prefix = f"chummer-install-linking-cutover-{suffix}-"
    if not container_name.startswith(prefix):
        raise SystemExit(1)
    job_name = container_name[len(prefix):]
    if (
        job_name != "prove-local-store-state"
        and re.fullmatch(
            r"postquiesce-[a-z0-9][a-z0-9-]{7,31}-"
            r"prove-local-store-state",
            job_name,
        )
        is None
    ):
        raise SystemExit(1)
    job_hash = hashlib.sha256(job_name.encode("utf-8")).hexdigest()[:12]
    expected_project = f"chummer6-ilpg-{suffix[:16]}-{job_hash}"
    if (
        image_id != candidate_tool_image_id
        or running is not False
        or mount["RW"] is not False
        or project != expected_project
        or service
        != "chummer-install-linking-postgres-import-presence-proof"
        or oneoff != "False"
    ):
        raise SystemExit(1)
    classification = "governed_local_store_proof"
record = {
    "classification": classification,
    "composeOneoff": oneoff,
    "composeProject": project,
    "composeService": service,
    "containerId": container_id,
    "containerName": container_name,
    "imageId": image_id,
    "jobName": job_name,
    "readWrite": mount["RW"],
    "running": running,
    "volumeDestination": mount["Destination"],
}
print(
    json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False),
    end="",
)
' "$container_id" "$CANONICAL_INSTALL_LINKING_STATE_VOLUME" \
        "$INSTALL_LINKING_CUTOVER_ID" "$prior_portal_container_id" \
        "$prior_portal_container_name" "$prior_portal_image_id" \
        "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID"
    )" || return 1
    printf '%s\n' "$parsed_record"
  done <<<"$identifiers"
}

write_install_linking_state_volume_inventory() {
  local checkpoint="$1"
  local output="$2"
  local first_inventory second_inventory
  first_inventory="$(capture_install_linking_state_volume_consumers_once)" \
    || return 1
  second_inventory="$(capture_install_linking_state_volume_consumers_once)" \
    || return 1
  [[ "$first_inventory" == "$second_inventory" ]] || return 1
  printf '%s' "$second_inventory" | trusted_source_python -c '
# InstallLinking state-volume inventory publisher.
import hashlib, json, os, pathlib, re, stat, sys, tempfile

output = pathlib.Path(sys.argv[1])
checkpoint = sys.argv[2]
attempt_id = sys.argv[3]
cutover_id = sys.argv[4]
volume_name = sys.argv[5]
incumbent_id = sys.argv[6]
candidate_tool_image_id = sys.argv[7]
mutation_lock_token_sha256 = sys.argv[8]
expected_name = (
    "INSTALL_LINKING_STATE_VOLUME_INVENTORY."
    f"{checkpoint.replace(chr(95), chr(45))}.{attempt_id}.json"
)
if (
    not output.is_absolute()
    or output.name != expected_name
    or checkpoint not in {
        "post_incumbent_quiesce",
        "pre_overlay_activation",
    }
    or re.fullmatch(r"[a-z0-9][a-z0-9-]{7,31}", attempt_id) is None
    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}", cutover_id)
    is None
    or volume_name != "chummer6-hub_chummer-run-api-state"
    or (
        incumbent_id
        and re.fullmatch(r"[0-9a-f]{64}", incumbent_id) is None
    )
    or re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_tool_image_id) is None
    or re.fullmatch(r"[0-9a-f]{64}", mutation_lock_token_sha256) is None
):
    raise SystemExit(1)
current = pathlib.Path(output.anchor)
for component in output.parent.parts[1:]:
    current /= component
    metadata = current.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise SystemExit(1)
parent_metadata = output.parent.lstat()
if (
    not stat.S_ISDIR(parent_metadata.st_mode)
    or parent_metadata.st_uid != os.getuid()
    or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    or output.exists()
    or output.is_symlink()
):
    raise SystemExit(1)
consumers = []
for line in sys.stdin.read().splitlines():
    if not line:
        raise SystemExit(1)
    consumers.append(json.loads(line))
if consumers != sorted(consumers, key=lambda item: item["containerId"]):
    raise SystemExit(1)
if len(consumers) != len({item["containerId"] for item in consumers}):
    raise SystemExit(1)
consumer_bytes = json.dumps(
    consumers,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
).encode("utf-8")
payload = {
    "attemptId": attempt_id,
    "candidateToolImageId": candidate_tool_image_id,
    "checkpoint": checkpoint,
    "consumerCount": len(consumers),
    "consumerSetSha256": hashlib.sha256(consumer_bytes).hexdigest(),
    "consumers": consumers,
    "contractName": "chummer.install_linking_state_volume_inventory.v1",
    "cutoverId": cutover_id,
    "incumbentPortalContainerId": incumbent_id or None,
    "mutationLockTokenSha256": mutation_lock_token_sha256,
    "status": "pass",
    "volumeName": volume_name,
}
encoded = (
    json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
).encode("utf-8")
descriptor, temporary_name = tempfile.mkstemp(
    prefix=f".{output.name}.",
    suffix=".tmp",
    dir=output.parent,
)
temporary = pathlib.Path(temporary_name)
try:
    os.fchmod(descriptor, 0o600)
    written = 0
    while written < len(encoded):
        written += os.write(descriptor, encoded[written:])
    os.fsync(descriptor)
finally:
    os.close(descriptor)
try:
    os.link(temporary, output, follow_symlinks=False)
finally:
    temporary.unlink(missing_ok=True)
metadata = output.lstat()
if (
    not stat.S_ISREG(metadata.st_mode)
    or metadata.st_nlink != 1
    or metadata.st_uid != os.getuid()
    or stat.S_IMODE(metadata.st_mode) != 0o600
):
    raise SystemExit(1)
parent_descriptor = os.open(
    output.parent,
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
)
try:
    os.fsync(parent_descriptor)
finally:
    os.close(parent_descriptor)
print(hashlib.sha256(encoded).hexdigest(), end="")
' "$output" "$checkpoint" "$INSTALL_LINKING_REPROOF_ATTEMPT_ID" \
    "$INSTALL_LINKING_CUTOVER_ID" "$CANONICAL_INSTALL_LINKING_STATE_VOLUME" \
    "$prior_portal_container_id" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
    "$deploy_lock_token_digest"
}

verify_install_linking_state_volume_inventory_transition() {
  local before_path="$1"
  local before_sha256="$2"
  local after_path="$3"
  local after_sha256="$4"
  trusted_source_python -c '
# InstallLinking state-volume inventory transition verifier.
import hashlib, json, os, pathlib, re, stat, sys

def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result

def read_private(path_value, expected_sha256):
    path = pathlib.Path(path_value)
    if (
        not path.is_absolute()
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
    ):
        raise ValueError("invalid input")
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ValueError("unsafe receipt")
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        before = os.fstat(descriptor)
        raw = bytearray()
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError("oversized")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    final = path.lstat()
    identity = (
        before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
        before.st_ctime_ns, before.st_nlink, stat.S_IMODE(before.st_mode),
    )
    if (
        identity
        != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
            after.st_ctime_ns, after.st_nlink, stat.S_IMODE(after.st_mode),
        )
        or identity
        != (
            final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns,
            final.st_ctime_ns, final.st_nlink, stat.S_IMODE(final.st_mode),
        )
        or hashlib.sha256(raw).hexdigest() != expected_sha256
    ):
        raise ValueError("receipt drift")
    return json.loads(
        bytes(raw).decode("utf-8"),
        object_pairs_hook=reject_duplicates,
    )

before = read_private(sys.argv[1], sys.argv[2])
after = read_private(sys.argv[3], sys.argv[4])
expected_keys = {
    "attemptId", "candidateToolImageId", "checkpoint", "consumerCount",
    "consumerSetSha256", "consumers", "contractName", "cutoverId",
    "incumbentPortalContainerId", "mutationLockTokenSha256", "status",
    "volumeName",
}
if (
    set(before) != expected_keys
    or set(after) != expected_keys
    or before.get("contractName")
    != "chummer.install_linking_state_volume_inventory.v1"
    or after.get("contractName") != before.get("contractName")
    or before.get("status") != "pass"
    or after.get("status") != "pass"
    or before.get("checkpoint") != "post_incumbent_quiesce"
    or after.get("checkpoint") != "pre_overlay_activation"
):
    raise SystemExit(1)
for key in (
    "attemptId", "candidateToolImageId", "cutoverId",
    "incumbentPortalContainerId", "mutationLockTokenSha256", "volumeName",
):
    if after.get(key) != before.get(key):
        raise SystemExit(1)
before_consumers = before.get("consumers")
after_consumers = after.get("consumers")
if not isinstance(before_consumers, list) or not isinstance(after_consumers, list):
    raise SystemExit(1)
def verify_set(payload, consumers):
    encoded = json.dumps(
        consumers,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if (
        payload.get("consumerCount") != len(consumers)
        or payload.get("consumerSetSha256")
        != hashlib.sha256(encoded).hexdigest()
    ):
        raise SystemExit(1)
verify_set(before, before_consumers)
verify_set(after, after_consumers)
before_by_id = {item.get("containerId"): item for item in before_consumers}
after_by_id = {item.get("containerId"): item for item in after_consumers}
if len(before_by_id) != len(before_consumers) or len(after_by_id) != len(after_consumers):
    raise SystemExit(1)
if any(after_by_id.get(identifier) != item for identifier, item in before_by_id.items()):
    raise SystemExit(1)
additions = [
    item for identifier, item in after_by_id.items()
    if identifier not in before_by_id
]
attempt_id = before.get("attemptId")
expected_job = f"postquiesce-{attempt_id}-prove-local-store-state"
if (
    len(additions) != 1
    or additions[0].get("classification")
    != "governed_local_store_proof"
    or additions[0].get("jobName") != expected_job
    or additions[0].get("running") is not False
    or additions[0].get("readWrite") is not False
):
    raise SystemExit(1)
' "$before_path" "$before_sha256" "$after_path" "$after_sha256"
}

if ! prior_tool_image_tag_id="$(resolve_image_tag_id "$TOOL_IMAGE_TAG")"; then
  echo "could not query prior PostgreSQL tool image tag identity" >&2
  exit 3
fi
for prior_tag_id in "$prior_image_tag_id" "$prior_tool_image_tag_id"; do
  if [[ -n "$prior_tag_id" && ! "$prior_tag_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "a prior canonical image tag identity is invalid" >&2
    exit 3
  fi
done
if [[ "$prior_image_tag_id" != "$INSTALL_LINKING_PRIOR_PORTAL_TAG_ID" \
  || "$prior_tool_image_tag_id" != "$INSTALL_LINKING_PRIOR_TOOL_TAG_ID" ]]; then
  echo "canonical portal or tool tag changed after the governed candidate build" >&2
  exit 3
fi

if ! active_runtime_authority="$(resolve_active_runtime_authority)"; then
  echo "could not validate active public-edge runtime authority" >&2
  exit 3
fi
IFS='|' read -r runtime_authority_state runtime_authority_existed \
  prior_portal_container_id runtime_authority_container_name \
  runtime_authority_image_id runtime_authority_was_running \
  runtime_authority_proof_authority_sha256 runtime_authority_proof_public_sha256 \
  <<<"$active_runtime_authority"
if [[ "$runtime_authority_state" == unmanaged ]]; then
  if ! prior_portal_container_id="$(compose_cli ps --all -q chummer-portal)"; then
    echo "could not query prior public-edge portal container" >&2
    exit 3
  fi
  if [[ "$prior_portal_container_id" == *$'\n'* ]]; then
    echo "public-edge portal resolved to more than one prior container" >&2
    exit 3
  fi
elif [[ "$runtime_authority_state" != managed \
  || "$runtime_authority_existed" != "0" && "$runtime_authority_existed" != "1" ]]; then
  echo "active public-edge runtime authority is invalid" >&2
  exit 3
fi
prior_portal_image_id=""
prior_portal_container_name=""
prior_portal_proof_authority_mount_sha256=""
prior_portal_proof_public_mount_sha256=""
prior_portal_was_running=0
prior_portal_existed=0
if [[ -n "$prior_portal_container_id" ]]; then
  prior_portal_existed=1
  prior_portal_container_id="$(docker_cli container inspect --format '{{.Id}}' \
    "$prior_portal_container_id")" || exit 3
  [[ "$prior_portal_container_id" =~ ^[0-9a-f]{64}$ ]] || exit 3
  prior_portal_image_id="$(docker_cli container inspect --format '{{.Image}}' \
    "$prior_portal_container_id")" || exit 3
  prior_portal_container_name="$(docker_cli container inspect --format '{{.Name}}' \
    "$prior_portal_container_id")" || exit 3
  prior_portal_container_name="${prior_portal_container_name#/}"
  prior_portal_running_state="$(docker_cli container inspect --format '{{.State.Running}}' \
    "$prior_portal_container_id")" || exit 3
  [[ "$prior_portal_image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 3
  [[ "$prior_portal_container_name" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]] || exit 3
  if [[ "$runtime_authority_state" == managed \
    && "$prior_portal_container_name" != "$runtime_authority_container_name" ]]; then
    echo "active runtime container name conflicts with its authority receipt" >&2
    exit 3
  fi
  if [[ "$runtime_authority_state" == managed \
    && "$prior_portal_image_id" != "$runtime_authority_image_id" ]]; then
    echo "active runtime container image conflicts with its authority receipt" >&2
    exit 3
  fi
  case "$prior_portal_running_state" in
    true)
      if [[ "$runtime_authority_state" == managed \
        && "$runtime_authority_was_running" != "1" ]]; then
        echo "active runtime running state conflicts with its authority receipt" >&2
        exit 3
      fi
      prior_portal_was_running=1
      prior_portal_proof_authority_mount_sha256="$(
        container_proof_sha256_by_id "$prior_portal_container_id" \
          /proofs/HUB_LOCAL_RELEASE_PROOF.generated.json
      )" || exit 3
      prior_portal_proof_public_mount_sha256="$(
        container_proof_sha256_by_id "$prior_portal_container_id" \
          /app/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json
      )" || exit 3
      if [[ "$prior_portal_proof_authority_mount_sha256" \
        != "$prior_portal_proof_public_mount_sha256" ]]; then
        echo "prior portal proof mounts cannot be recreated from one bind source" >&2
        exit 3
      fi
      if [[ "$runtime_authority_state" == managed \
        && ( "$prior_portal_proof_authority_mount_sha256" \
          != "$runtime_authority_proof_authority_sha256" \
          || "$prior_portal_proof_public_mount_sha256" \
          != "$runtime_authority_proof_public_sha256" ) ]]; then
        echo "active runtime proof mounts conflict with their authority receipt" >&2
        exit 3
      fi
      # Docker's archive-based `container cp` tries to reopen every nested bind
      # below the read-only /app mount and fails before it can copy either proof.
      # Stream each already hash-verified file through container exec instead;
      # the receiver is bounded, digest-gated, mode-0600, and no-clobber.
      snapshot_container_proof_by_id \
        "$prior_portal_container_id" \
        /proofs/HUB_LOCAL_RELEASE_PROOF.generated.json \
        "$PRIOR_PROOF_AUTHORITY_SNAPSHOT" \
        "$prior_portal_proof_authority_mount_sha256" || exit 3
      snapshot_container_proof_by_id \
        "$prior_portal_container_id" \
        /app/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json \
        "$PRIOR_PROOF_PUBLIC_SNAPSHOT" \
        "$prior_portal_proof_public_mount_sha256" || exit 3
      prior_authority_snapshot_sha256="$(
        "$TRUSTED_SHA256SUM" -- "$PRIOR_PROOF_AUTHORITY_SNAPSHOT"
      )"
      prior_authority_snapshot_sha256="${prior_authority_snapshot_sha256%% *}"
      prior_public_snapshot_sha256="$(
        "$TRUSTED_SHA256SUM" -- "$PRIOR_PROOF_PUBLIC_SNAPSHOT"
      )"
      prior_public_snapshot_sha256="${prior_public_snapshot_sha256%% *}"
      [[ "$prior_authority_snapshot_sha256" \
        == "$prior_portal_proof_authority_mount_sha256" ]] || exit 3
      [[ "$prior_public_snapshot_sha256" \
        == "$prior_portal_proof_public_mount_sha256" ]] || exit 3
      ;;
    false)
      if [[ "$runtime_authority_state" == managed \
        && "$runtime_authority_was_running" != "0" ]]; then
        echo "active runtime running state conflicts with its authority receipt" >&2
        exit 3
      fi
      ;;
    *) exit 3 ;;
  esac
elif [[ "$runtime_authority_state" == managed ]]; then
  if [[ "$runtime_authority_existed" != "0" ]]; then
    echo "active runtime authority lost its portal container" >&2
    exit 3
  fi
  if ! unexpected_portal_container_ids="$(
    compose_cli ps --all -q chummer-portal
  )"; then
    echo "could not verify active runtime portal absence" >&2
    exit 3
  fi
  if [[ -n "$unexpected_portal_container_ids" ]]; then
    echo "active runtime authority claims absence while Compose resolves a portal" >&2
    exit 3
  fi
fi

existing_candidate_container_id="$(
  docker_cli container ls --all --quiet --no-trunc \
    --filter "name=^/${CANDIDATE_PORTAL_CONTAINER_NAME}$"
)" || exit 3
if [[ -n "$existing_candidate_container_id" ]]; then
  echo "generated public-edge candidate name is already occupied" >&2
  exit 3
fi

if ! prior_tunnel_container_id="$(
  compose_cli ps --all -q "$CANONICAL_TUNNEL_PRIMARY_SERVICE"
)"; then
  echo "could not query prior public-edge tunnel container" >&2
  exit 3
fi
if [[ "$prior_tunnel_container_id" == *$'\n'* ]]; then
  echo "public-edge tunnel resolved to more than one prior container" >&2
  exit 3
fi
prior_tunnel_image_id=""
prior_tunnel_was_running=0
prior_tunnel_existed=0
if [[ -n "$prior_tunnel_container_id" ]]; then
  prior_tunnel_existed=1
  prior_tunnel_container_id="$(docker_cli container inspect --format '{{.Id}}' \
    "$prior_tunnel_container_id")" || exit 3
  [[ "$prior_tunnel_container_id" =~ ^[0-9a-f]{64}$ ]] || exit 3
  prior_tunnel_image_id="$(docker_cli container inspect --format '{{.Image}}' \
    "$prior_tunnel_container_id")" || exit 3
  prior_tunnel_running_state="$(docker_cli container inspect --format '{{.State.Running}}' \
    "$prior_tunnel_container_id")" || exit 3
  [[ "$prior_tunnel_image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 3
  case "$prior_tunnel_running_state" in
    true) prior_tunnel_was_running=1 ;;
    false) ;;
    *) exit 3 ;;
  esac
fi
if ! prior_tunnel_replica_container_id="$(
  compose_cli ps --all -q "$CANONICAL_TUNNEL_REPLICA_SERVICE"
)"; then
  echo "could not query prior public-edge tunnel replica container" >&2
  exit 3
fi
if [[ "$prior_tunnel_replica_container_id" == *$'\n'* ]]; then
  echo "public-edge tunnel replica resolved to more than one prior container" >&2
  exit 3
fi
prior_tunnel_replica_image_id=""
prior_tunnel_replica_was_running=0
prior_tunnel_replica_existed=0
if [[ -n "$prior_tunnel_replica_container_id" ]]; then
  prior_tunnel_replica_existed=1
  prior_tunnel_replica_container_id="$(
    docker_cli container inspect --format '{{.Id}}' \
      "$prior_tunnel_replica_container_id"
  )" || exit 3
  [[ "$prior_tunnel_replica_container_id" =~ ^[0-9a-f]{64}$ ]] || exit 3
  if [[ "$prior_tunnel_replica_container_id" == "$prior_tunnel_container_id" ]]; then
    echo "canonical Cloudflare connectors resolved to the same container" >&2
    exit 3
  fi
  prior_tunnel_replica_image_id="$(
    docker_cli container inspect --format '{{.Image}}' \
      "$prior_tunnel_replica_container_id"
  )" || exit 3
  prior_tunnel_replica_running_state="$(
    docker_cli container inspect --format '{{.State.Running}}' \
      "$prior_tunnel_replica_container_id"
  )" || exit 3
  [[ "$prior_tunnel_replica_image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 3
  case "$prior_tunnel_replica_running_state" in
    true) prior_tunnel_replica_was_running=1 ;;
    false) ;;
    *) exit 3 ;;
  esac
fi

# The fixed journal is durable before Buildx can retag either canonical image.
prior_proof_authority_snapshot_argument=""
prior_proof_public_snapshot_argument=""
if ((prior_portal_was_running == 1)); then
  prior_proof_authority_snapshot_argument="$PRIOR_PROOF_AUTHORITY_SNAPSHOT"
  prior_proof_public_snapshot_argument="$PRIOR_PROOF_PUBLIC_SNAPSHOT"
fi
if ! trusted_source_python "$SOURCE_ROOT/scripts/public_edge_overlay_transaction.py" snapshot \
  --source-root "$SOURCE_ROOT" \
  --active-root "$OVERLAY_ROOT" \
  --output "$OVERLAY_PRIOR_STATE_OUTPUT" \
  --shared-mutation-lock-token "$deploy_lock_owner_token" \
  --expected-runtime-proof-bind-source-sha256 \
    "$RUNTIME_PROOF_BIND_SOURCE_SHA256" \
  --public-projection-snapshot-id "$PUBLIC_PROJECTION_SNAPSHOT_ID" \
  --public-projection-snapshot-sha256 "$PUBLIC_PROJECTION_SNAPSHOT_SHA256" \
  --public-projection-manifest-sha256 "$PUBLIC_PROJECTION_MANIFEST_SHA256" \
  --candidate-portal-container-name "$CANDIDATE_PORTAL_CONTAINER_NAME" \
  --prior-image-tag-id "$prior_image_tag_id" \
  --prior-tool-image-tag-id "$prior_tool_image_tag_id" \
  --prior-portal-container-id "$prior_portal_container_id" \
  --prior-portal-container-name "$prior_portal_container_name" \
  --prior-portal-image-id "$prior_portal_image_id" \
  --prior-portal-proof-authority-mount-sha256 \
    "$prior_portal_proof_authority_mount_sha256" \
  --prior-portal-proof-public-mount-sha256 \
    "$prior_portal_proof_public_mount_sha256" \
  --prior-portal-existed "$prior_portal_existed" \
  --prior-portal-was-running "$prior_portal_was_running" \
  --prior-tunnel-container-id "$prior_tunnel_container_id" \
  --prior-tunnel-image-id "$prior_tunnel_image_id" \
  --prior-tunnel-existed "$prior_tunnel_existed" \
  --prior-tunnel-was-running "$prior_tunnel_was_running" \
  --prior-tunnel-replica-container-id "$prior_tunnel_replica_container_id" \
  --prior-tunnel-replica-image-id "$prior_tunnel_replica_image_id" \
  --prior-tunnel-replica-existed "$prior_tunnel_replica_existed" \
  --prior-tunnel-replica-was-running "$prior_tunnel_replica_was_running" \
  --staging-root "$OVERLAY_STAGING_ROOT" \
  --backup-root "$OVERLAY_BACKUP_ROOT" \
  --activation-receipt "$OVERLAY_ACTIVATION_OUTPUT" \
  --proof-bind-source "$RUNTIME_PROOF_BIND_SOURCE" \
  --candidate-proof-bind-source-snapshot \
    "$CANDIDATE_PROOF_BIND_SOURCE_SNAPSHOT" \
  --prior-portal-proof-authority-snapshot \
    "$prior_proof_authority_snapshot_argument" \
  --prior-portal-proof-public-snapshot \
    "$prior_proof_public_snapshot_argument"; then
  "$TRUSTED_RM" -f -- "$OVERLAY_PRIOR_STATE_OUTPUT"
  exit 1
fi

deployment_transaction_active=1
precompletion_transaction_backup_active=0
install_linking_materializer_invoked=0
postquiesce_runner_invoked=0
postquiesce_outcome_resolved=0
retain_deploy_authority_on_exit=0
epoch_rotation_fail_forward_required=0
epoch_rotation_precommit_refused=0
reconcile_transaction_on_exit() {
  local failure_status="$?"
  local recovery_failed=0
  local exit_reconciled_boundary_sha256
  local exit_postquiesce_classification
  trap - EXIT HUP INT TERM
  if ((epoch_rotation_fail_forward_required == 1)); then
    printf \
      'release_upload_ticket_epoch_fail_forward_required lock=%s receipt=%s\n' \
      "$DEPLOY_LOCK_DIR" "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" >&2
    exit "$failure_status"
  fi
  if ((deployment_transaction_active == 1 \
    && postquiesce_runner_invoked == 1 \
    && postquiesce_outcome_resolved == 0)); then
    if exit_postquiesce_classification="$(
      classify_install_linking_postquiesce_attempt
    )" \
      && [[ "$exit_postquiesce_classification" \
        =~ ^safe_fail\|[0-9a-f]{64}$ ]]; then
      postquiesce_outcome_resolved=1
      printf \
        'install_linking_postquiesce_safe_fail_exit_reconciled receipt_sha256=%s\n' \
        "${exit_postquiesce_classification#safe_fail|}" >&2
    else
      retain_deploy_authority_on_exit=1
    fi
  fi
  if ((retain_deploy_authority_on_exit == 1)); then
    printf \
      'install_linking_postquiesce_unknown_authority_retained lock=%s journal=%s receipt=%s\n' \
      "$DEPLOY_LOCK_DIR" "$OVERLAY_PRIOR_STATE_OUTPUT" \
      "$INSTALL_LINKING_POSTQUIESCE_RECEIPT" >&2
    exit "$failure_status"
  fi
  if ((deployment_transaction_active == 1 \
    && install_linking_materializer_invoked == 1)); then
    if exit_reconciled_boundary_sha256="$(
      verify_install_linking_public_acceptance_boundary
    )"; then
      deployment_transaction_active=0
      precompletion_transaction_backup_active=0
      printf \
        'install_linking_public_acceptance_exit_reconciled boundary_sha256=%s\n' \
        "$exit_reconciled_boundary_sha256" >&2
    fi
  fi
  if ((deployment_transaction_active == 1)); then
    if ((precompletion_transaction_backup_active == 1)) \
      && [[ ! -e "$OVERLAY_PRIOR_STATE_OUTPUT" \
        && ! -L "$OVERLAY_PRIOR_STATE_OUTPUT" ]]; then
      if ! restored_transaction_sha256="$(
        publish_private_snapshot \
          "$PRECOMPLETION_TRANSACTION_BACKUP" \
          "$OVERLAY_PRIOR_STATE_OUTPUT" \
          raw \
          1
      )" \
        || [[ "$restored_transaction_sha256" \
          != "$precompletion_transaction_backup_sha256" ]]; then
        recovery_failed=1
      fi
    fi
    if ((recovery_failed == 0)); then
      run_deploy_recovery || recovery_failed=1
    fi
  fi
  release_deploy_lock || recovery_failed=1
  if ((recovery_failed == 1)); then
    exit 70
  fi
  exit "$failure_status"
}

trap reconcile_transaction_on_exit EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if ! mark_deploy_phase image_build_started; then
  abort_portal_recreate "candidate image promotion journal" 1
fi

# The governed cutover runner already built both images from the exact clean
# source under unique, retained tags. The durable transaction above captured
# the incumbent canonical tag IDs before either tag can be repointed.
# Keep those exact IDs reachable under content-addressed recovery tags as well.
# Docker may discard an unreferenced image immediately after a canonical tag is
# repointed, which would otherwise make the durable rollback journal truthful
# but unusable.
if [[ -n "$prior_image_tag_id" ]] \
  && ! docker_cli image tag \
    "$prior_image_tag_id" \
    "chummer-run-api:recovery-${prior_image_tag_id#sha256:}"; then
  abort_portal_recreate "prior portal image retention" 1
fi
if [[ -n "$prior_tool_image_tag_id" ]] \
  && ! docker_cli image tag \
    "$prior_tool_image_tag_id" \
    "chummer-install-linking-postgres-tool:recovery-${prior_tool_image_tag_id#sha256:}"; then
  abort_portal_recreate "prior PostgreSQL tool image retention" 1
fi
if ! docker_cli image tag \
  "$INSTALL_LINKING_CANDIDATE_PORTAL_TAG" "$IMAGE_TAG" \
  || ! docker_cli image tag \
    "$INSTALL_LINKING_CANDIDATE_TOOL_TAG" "$TOOL_IMAGE_TAG"; then
  abort_portal_recreate "candidate image promotion" 1
fi
if ! image_id="$(resolve_exact_image_id "$IMAGE_TAG")" \
  || ! tool_image_id="$(resolve_exact_image_id "$TOOL_IMAGE_TAG")" \
  || ! retained_candidate_image_id="$(
    resolve_exact_image_id "$INSTALL_LINKING_CANDIDATE_PORTAL_TAG"
  )" \
  || ! retained_candidate_tool_image_id="$(
    resolve_exact_image_id "$INSTALL_LINKING_CANDIDATE_TOOL_TAG"
  )"; then
  abort_portal_recreate "candidate image promotion identity" 1
fi
if [[ "$image_id" != "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
  || "$tool_image_id" != "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
  || "$retained_candidate_image_id" != "$image_id" \
  || "$retained_candidate_tool_image_id" != "$tool_image_id" ]]; then
  abort_portal_recreate "candidate image ID comparison" 1
fi
if ! mark_deploy_phase image_built; then
  abort_portal_recreate "candidate image promotion completion journal" 1
fi

# Rebind the source-only gate after the image build. A source mutation between
# verified staging and this point fails while the exact prior runtime is live.
trusted_source_python "$SOURCE_ROOT/scripts/check_public_edge_deploy_preflight.py" \
  --source-root "$SOURCE_ROOT" \
  --skip-overlay-marker-check \
  --public-projection-snapshot-root "$PROJECTION_SNAPSHOT_ROOT" \
  --public-projection-purpose code-deploy \
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256" \
  --runtime-proof-bind-source-sha256 "$RUNTIME_PROOF_BIND_SOURCE_SHA256"

if ! predrain_portal_tag_id="$(resolve_exact_image_id "$IMAGE_TAG")" \
  || ! predrain_tool_tag_id="$(resolve_exact_image_id "$TOOL_IMAGE_TAG")" \
  || ! predrain_candidate_portal_id="$(
    resolve_exact_image_id "$INSTALL_LINKING_CANDIDATE_PORTAL_TAG"
  )" \
  || ! predrain_candidate_tool_id="$(
    resolve_exact_image_id "$INSTALL_LINKING_CANDIDATE_TOOL_TAG"
  )" \
  || [[ "$predrain_portal_tag_id" != "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
    || "$predrain_candidate_portal_id" != "$predrain_portal_tag_id" \
    || "$predrain_tool_tag_id" \
      != "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
    || "$predrain_candidate_tool_id" != "$predrain_tool_tag_id" ]]; then
  abort_portal_recreate "predrain candidate image identity" 1
fi
if ! predrain_boundary_verification="$(
  verify_install_linking_cutover_boundary \
    "$INSTALL_LINKING_CUTOVER_BOUNDARY_SHA256" \
    validate_completed \
    "$predrain_candidate_portal_id" \
    "$predrain_candidate_tool_id"
)" \
  || [[ "$predrain_boundary_verification" \
    != "$install_linking_boundary_verification" ]]; then
  abort_portal_recreate "predrain InstallLinking boundary identity" 1
fi

if ! compose_cli stop chummer-run-cloudflared; then
  abort_portal_recreate "primary tunnel drain" 1
fi
if ! compose_cli stop chummer-run-cloudflared-replica; then
  abort_portal_recreate "replica tunnel drain" 1
fi
if ! mark_deploy_phase tunnel_drained; then
  abort_portal_recreate "canonical tunnel drain journal" 1
fi
if ((prior_portal_existed == 1 && prior_portal_was_running == 1)) \
  && ! docker_cli container stop "$prior_portal_container_id" >/dev/null; then
  abort_portal_recreate "prior portal quiesce" 1
fi
if ! mark_deploy_phase portal_stopped; then
  abort_portal_recreate "portal stop journal" 1
fi

if ! INSTALL_LINKING_POSTQUIESCE_VOLUME_INVENTORY_SHA256="$(
  write_install_linking_state_volume_inventory \
    post_incumbent_quiesce \
    "$INSTALL_LINKING_POSTQUIESCE_VOLUME_INVENTORY"
)" \
  || [[ ! "$INSTALL_LINKING_POSTQUIESCE_VOLUME_INVENTORY_SHA256" \
    =~ ^[0-9a-f]{64}$ ]]; then
  abort_portal_recreate "post-quiesce state-volume consumer inventory" 1
fi

# With the incumbent portal and both canonical tunnel connectors quiesced,
# repeat the metadata-only local-state, seeded-authority, and runtime-role
# proofs from the exact retained
# candidate tool image. The runner inherits this wrapper's canonical mutation
# lease and preserves every job container/receipt on ambiguous outcomes.
postquiesce_status=0
postquiesce_runner_invoked=1
trusted_source_python "$INSTALL_LINKING_CUTOVER_RUNNER" \
  --post-quiesce-reproof \
  --reproof-attempt-id "$INSTALL_LINKING_REPROOF_ATTEMPT_ID" \
  --source-root "$INSTALL_LINKING_POSTQUIESCE_SOURCE_ROOT" \
  "${install_linking_source_replay_args[@]}" \
  --expected-head "${EXPECTED_HEAD,,}" \
  --expected-compose-sha256 "$INSTALL_LINKING_COMPOSE_SHA256" \
  --env-file "$ENV_FILE" \
  --expected-env-sha256 "$INSTALL_LINKING_ENV_SHA256" \
  --expected-runner-sha256 "$INSTALL_LINKING_RUNNER_SHA256" \
  --expected-hub-registry-head \
    "$INSTALL_LINKING_EXPECTED_HUB_REGISTRY_HEAD" \
  --expected-design-product-head \
    "$INSTALL_LINKING_EXPECTED_DESIGN_PRODUCT_HEAD" \
  --expected-fleet-media-factory-head \
    "$INSTALL_LINKING_EXPECTED_FLEET_MEDIA_FACTORY_HEAD" \
  --expected-build-context-dockerignore-sha256 \
    "$INSTALL_LINKING_EXPECTED_BUILD_CONTEXT_DOCKERIGNORE_SHA256" \
  --cutover-id "$INSTALL_LINKING_CUTOVER_ID" \
  --receipt-root "$INSTALL_LINKING_CUTOVER_RECEIPT_ROOT" \
  --boundary-output "$INSTALL_LINKING_CUTOVER_BOUNDARY" \
  --expected-boundary-sha256 "$INSTALL_LINKING_CUTOVER_BOUNDARY_SHA256" \
  --expected-candidate-image-id \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
  --expected-candidate-tool-image-id \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
  --shared-mutation-lock-token "$deploy_lock_owner_token" \
  --volume-inventory-receipt \
    "$INSTALL_LINKING_POSTQUIESCE_VOLUME_INVENTORY" \
  --expected-volume-inventory-sha256 \
    "$INSTALL_LINKING_POSTQUIESCE_VOLUME_INVENTORY_SHA256" \
  --output "$INSTALL_LINKING_POSTQUIESCE_RECEIPT" \
  >/dev/null || postquiesce_status=$?
if ! postquiesce_classification="$(
  classify_install_linking_postquiesce_attempt
)" \
  || [[ ! "$postquiesce_classification" \
    =~ ^(pass|safe_fail|unknown)\|([0-9a-f]{64})$ ]]; then
  retain_unknown_postquiesce_authority \
    "post-quiesce InstallLinking receipt classification"
fi
INSTALL_LINKING_POSTQUIESCE_RECEIPT_SHA256="${BASH_REMATCH[2]}"
case "${BASH_REMATCH[1]}" in
  pass)
    if ! install_linking_postquiesce_runtime_authority="$(
      bind_install_linking_postquiesce_runtime_authority_identity
    )" \
      || [[ ! "$install_linking_postquiesce_runtime_authority" \
        =~ ^([0-9a-f]{64})\|([0-9a-f]{64})$ ]]; then
      retain_unknown_postquiesce_authority \
        "post-quiesce InstallLinking runtime authority binding"
    fi
    INSTALL_LINKING_EXPECTED_AUTHORITY_IDENTITY_SHA256="${BASH_REMATCH[1]}"
    INSTALL_LINKING_EXPECTED_RUNTIME_ROLE_SHA256="${BASH_REMATCH[2]}"
    postquiesce_outcome_resolved=1
    ;;
  safe_fail)
    postquiesce_outcome_resolved=1
    abort_portal_recreate \
      "post-quiesce InstallLinking verified safe failure (runner exit ${postquiesce_status})" \
      1
    ;;
  unknown)
    retain_unknown_postquiesce_authority \
      "post-quiesce InstallLinking proof (runner exit ${postquiesce_status})"
    ;;
esac

if ! INSTALL_LINKING_PREACTIVATION_VOLUME_INVENTORY_SHA256="$(
  write_install_linking_state_volume_inventory \
    pre_overlay_activation \
    "$INSTALL_LINKING_PREACTIVATION_VOLUME_INVENTORY"
)" \
  || [[ ! "$INSTALL_LINKING_PREACTIVATION_VOLUME_INVENTORY_SHA256" \
    =~ ^[0-9a-f]{64}$ ]]; then
  retain_unknown_postquiesce_authority \
    "pre-activation state-volume consumer inventory"
fi
if ! verify_install_linking_state_volume_inventory_transition \
  "$INSTALL_LINKING_POSTQUIESCE_VOLUME_INVENTORY" \
  "$INSTALL_LINKING_POSTQUIESCE_VOLUME_INVENTORY_SHA256" \
  "$INSTALL_LINKING_PREACTIVATION_VOLUME_INVENTORY" \
  "$INSTALL_LINKING_PREACTIVATION_VOLUME_INVENTORY_SHA256"; then
  retain_unknown_postquiesce_authority \
    "pre-activation state-volume consumer transition"
fi

# Re-render and attest the exact Compose runtime immediately before the overlay
# exchange. This closes the gap between the earlier source/build gate and
# recreation: an empty, HTTP, or otherwise stale canonical origin and any mount
# destination drift fail while the durable transaction can still restore the
# incumbent. The new compatibility sections persist only public-value digests and
# container destinations; they do not duplicate bind-source bytes.
if ! compose_cli --profile install-linking-postgres-admin config --format json \
  | trusted_source_python "$SOURCE_ROOT/scripts/validate_public_edge_compose_runtime.py" \
      --operation "$COMPOSE_ATTESTATION_OPERATION" \
      --project-name "$COMPOSE_PROJECT" \
      --source-root "$SOURCE_ROOT" \
      --build-context "$BUILD_CONTEXT" \
      --overlay-root "$OVERLAY_ROOT" \
      --projection-root "$PROJECTION_SNAPSHOT_ROOT" \
      --runtime-proof-bind-source "$RUNTIME_PROOF_BIND_SOURCE" \
      --published-port "$PUBLIC_EDGE_PORT" \
      --output "$PREACTIVATION_COMPOSE_ATTESTATION_OUTPUT"; then
  abort_portal_recreate "pre-activation Compose runtime compatibility" 1
fi

# The stopped portal no longer has the active root bind-mounted. Reuse-staging
# revalidates the candidate's recorded source fingerprint and performs the
# publisher's atomic exchange while inheriting this transaction's shared lock.
if ! trusted_source_python "$SOURCE_ROOT/scripts/publish_public_edge_portal_overlay.py" \
  --activate \
  --reuse-staging \
  --shared-mutation-lock-token "$deploy_lock_owner_token" \
  --source-root "$SOURCE_ROOT" \
  --active-root "$OVERLAY_ROOT" \
  --staging-root "$OVERLAY_STAGING_ROOT" \
  --backup-root "$OVERLAY_BACKUP_ROOT" \
  --build-root "$OVERLAY_BUILD_ROOT" \
  --host-build-root "$PUBLIC_EDGE_HOST_BUILD_ROOT" \
  --downloads-source-root "$CANONICAL_RELEASE_SHELF_ROOT" \
  --playwright-authority "$PLAYWRIGHT_AUTHORITY" \
  --playwright-authority-sha256 "$PLAYWRIGHT_AUTHORITY_SHA256" \
  --surface-profile public-download \
  --delivery-phase windows-preview \
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256" \
  --output "$OVERLAY_ACTIVATION_OUTPUT"; then
  abort_portal_recreate "overlay activation" 1
fi
if ! mark_deploy_phase overlay_activated; then
  abort_portal_recreate "overlay activation journal" 1
fi

if ! compose_cli run --rm --no-deps chummer-portal-volume-init; then
  abort_portal_recreate "volume initialization" 1
fi

# This is the first full preflight: active-overlay identity is meaningful only
# after the verified candidate has been selected while the old portal is drained.
# It runs after volume initialization and immediately before portal recreation.
if ! trusted_source_python "$SOURCE_ROOT/scripts/check_public_edge_deploy_preflight.py" \
  --source-root "$SOURCE_ROOT" \
  --overlay-root "$OVERLAY_ROOT" \
  --public-projection-snapshot-root "$PROJECTION_SNAPSHOT_ROOT" \
  --public-projection-purpose code-deploy \
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256" \
  --runtime-proof-bind-source-sha256 "$RUNTIME_PROOF_BIND_SOURCE_SHA256" \
  --output "$OVERLAY_ACTIVE_PREFLIGHT_OUTPUT"; then
  abort_portal_recreate "active overlay preflight" 1
fi

wait_for_candidate_portal_runtime() {
  local deadline=$((SECONDS + PORTAL_READY_TIMEOUT_SECONDS))
  local running health
  while ((SECONDS < deadline)); do
    running="$(docker_cli container inspect --format '{{.State.Running}}' \
      "$candidate_portal_container_id")" || return 1
    health="$(docker_cli container inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
      "$candidate_portal_container_id")" || return 1
    if [[ "$running" == true && "$health" == healthy ]]; then
      return 0
    fi
    if [[ "$running" != true || "$health" == unhealthy ]]; then
      return 1
    fi
    "$TRUSTED_SLEEP" 1
  done
  return 1
}

start_candidate_portal() {
  local candidate_portal_create_output
  # Do not add --rm: the durable outer reconciliation journal owns exact
  # candidate cleanup on every failure.
  candidate_portal_create_output="$(
    compose_cli run -T -d --no-deps --service-ports --use-aliases \
      --name "$CANDIDATE_PORTAL_CONTAINER_NAME" chummer-portal
  )" || return 1
  candidate_portal_container_id="$(
    docker_cli container inspect --format '{{.Id}}' \
      "$CANDIDATE_PORTAL_CONTAINER_NAME"
  )" || return 1
  [[ "$candidate_portal_container_id" =~ ^[0-9a-f]{64}$ \
    && -n "$candidate_portal_create_output" ]]
}

verify_candidate_publication_readiness() {
  local attempt probe_status
  for attempt in 1 2 3; do
    probe_status=0
    "$TRUSTED_TIMEOUT" --kill-after=5s 30s \
      "${docker_command[@]}" container exec "$candidate_portal_container_id" \
        dotnet /app/loopback-probe/Chummer.Run.LoopbackProbe.dll \
          /api/ready/publication >/dev/null || probe_status="$?"
    if ((probe_status == 0)); then
      return 0
    fi
    # The audited loopback probe returns one for a well-bounded negative
    # readiness assessment. Retry only that transient result; invocation,
    # timeout, and policy failures remain fail-closed without delay.
    if ((probe_status != 1 || attempt == 3)); then
      return 1
    fi
    "$TRUSTED_SLEEP" 2
  done
  return 1
}

capture_candidate_publication_readiness() {
  local body_file readiness_http_status response_sha256
  local observed_id observed_name observed_image observed_running observed_health
  body_file="$($TRUSTED_MKTEMP -- "$DEPLOY_RECEIPT_DIR/.publication-readiness-body.XXXXXXXX")" \
    || return 1
  "$TRUSTED_CHMOD" 0600 -- "$body_file" || {
    "$TRUSTED_RM" -f -- "$body_file"
    return 1
  }
  if ! "$TRUSTED_TIMEOUT" --kill-after=5s 30s \
    "${docker_command[@]}" container exec "$candidate_portal_container_id" \
      dotnet /app/loopback-probe/Chummer.Run.LoopbackProbe.dll \
        /api/ready/publication >"$body_file"; then
    "$TRUSTED_RM" -f -- "$body_file"
    return 1
  fi
  readiness_http_status=200
  response_sha256="$($TRUSTED_SHA256SUM -- "$body_file")"
  response_sha256="${response_sha256%% *}"
  [[ "$response_sha256" =~ ^[0-9a-f]{64}$ ]] || {
    "$TRUSTED_RM" -f -- "$body_file"
    return 1
  }
  if ! observed_id="$(docker_cli container inspect --format '{{.Id}}' \
    "$candidate_portal_container_id")" \
    || ! observed_name="$(docker_cli container inspect --format '{{.Name}}' \
      "$candidate_portal_container_id")" \
    || ! observed_image="$(docker_cli container inspect --format '{{.Image}}' \
      "$candidate_portal_container_id")" \
    || ! observed_running="$(docker_cli container inspect --format '{{.State.Running}}' \
      "$candidate_portal_container_id")" \
    || ! observed_health="$(docker_cli container inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
      "$candidate_portal_container_id")"; then
    "$TRUSTED_RM" -f -- "$body_file"
    return 1
  fi
  observed_name="${observed_name#/}"
  if [[ "$observed_id" != "$candidate_portal_container_id" \
    || "$observed_name" != "$CANDIDATE_PORTAL_CONTAINER_NAME" \
    || "$observed_image" != "$image_id" \
    || "$observed_running" != true \
    || "$observed_health" != healthy ]]; then
    "$TRUSTED_RM" -f -- "$body_file"
    return 1
  fi
  if ! trusted_source_python "$CUTOVER_ATTESTOR" record-readiness \
    --output "$PUBLICATION_READINESS_ATTESTATION" \
    --candidate-container-id "$observed_id" \
    --candidate-container-name "$observed_name" \
    --candidate-image-id "$observed_image" \
    --http-status "$readiness_http_status" \
    --response-sha256 "$response_sha256" \
    --running "$observed_running" \
    --health "$observed_health" >/dev/null; then
    "$TRUSTED_RM" -f -- "$body_file"
    return 1
  fi
  "$TRUSTED_RM" -f -- "$body_file"
}

capture_candidate_install_linking_authority_readiness() {
  local body_file observed_id observed_name observed_image
  local observed_running observed_health
  body_file="$(
    "$TRUSTED_MKTEMP" -- \
      "$DEPLOY_RECEIPT_DIR/.install-linking-authority-body.XXXXXXXX"
  )" || return 1
  "$TRUSTED_CHMOD" 0600 -- "$body_file" || {
    "$TRUSTED_RM" -f -- "$body_file"
    return 1
  }
  if ! "$TRUSTED_TIMEOUT" --kill-after=5s 30s \
    "${docker_command[@]}" container exec "$candidate_portal_container_id" \
      dotnet /app/loopback-probe/Chummer.Run.LoopbackProbe.dll \
        /api/ready/install-linking-authority \
        >"$body_file"; then
    "$TRUSTED_RM" -f -- "$body_file"
    return 1
  fi
  if ! observed_id="$(docker_cli container inspect --format '{{.Id}}' \
    "$candidate_portal_container_id")" \
    || ! observed_name="$(docker_cli container inspect --format '{{.Name}}' \
      "$candidate_portal_container_id")" \
    || ! observed_image="$(docker_cli container inspect --format '{{.Image}}' \
      "$candidate_portal_container_id")" \
    || ! observed_running="$(docker_cli container inspect --format '{{.State.Running}}' \
      "$candidate_portal_container_id")" \
    || ! observed_health="$(docker_cli container inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
      "$candidate_portal_container_id")"; then
    "$TRUSTED_RM" -f -- "$body_file"
    return 1
  fi
  observed_name="${observed_name#/}"
  if [[ "$observed_id" != "$candidate_portal_container_id" \
    || "$observed_name" != "$CANDIDATE_PORTAL_CONTAINER_NAME" \
    || "$observed_image" != "$image_id" \
    || "$observed_running" != true \
    || "$observed_health" != healthy ]]; then
    "$TRUSTED_RM" -f -- "$body_file"
    return 1
  fi
  INSTALL_LINKING_RUNTIME_AUTHORITY_READINESS_SHA256="$(
    trusted_source_python -c '
# InstallLinking live runtime authority readiness publisher.
import hashlib, json, os, pathlib, re, stat, sys, tempfile
from datetime import datetime, timedelta

def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result

def read_private(path, *, maximum):
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size < 1
            or before.st_size > maximum
        ):
            raise ValueError("unsafe private response")
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                raise ValueError("short private response")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError("oversized private response")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("private response changed while open")
        return b"".join(chunks)
    finally:
        os.close(descriptor)

body = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
expected_authority = sys.argv[3]
expected_role = sys.argv[4]
if (
    not output.is_absolute()
    or re.fullmatch(
        r"install-linking-authority-readiness-[A-Za-z0-9]{8}\.json",
        output.name,
    )
    is None
    or re.fullmatch(r"[0-9a-f]{64}", expected_authority) is None
    or re.fullmatch(r"[0-9a-f]{64}", expected_role) is None
):
    raise SystemExit(1)
current = pathlib.Path(output.anchor)
for component in output.parent.parts[1:]:
    current /= component
    if stat.S_ISLNK(current.lstat().st_mode):
        raise SystemExit(1)
parent = output.parent.lstat()
if (
    not stat.S_ISDIR(parent.st_mode)
    or parent.st_uid != os.getuid()
    or stat.S_IMODE(parent.st_mode) != 0o700
    or output.exists()
    or output.is_symlink()
):
    raise SystemExit(1)
try:
    payload = json.loads(
        read_private(body, maximum=4096).decode("utf-8"),
        object_pairs_hook=reject_duplicates,
    )
except (UnicodeError, ValueError, json.JSONDecodeError):
    raise SystemExit(1)
expected_keys = {
    "authorityIdentitySha256",
    "checkedAtUtc",
    "code",
    "contractName",
    "currentRoleMatches",
    "leastPrivilegeValid",
    "ready",
    "runtimeRoleSha256",
    "status",
}
if (
    not isinstance(payload, dict)
    or set(payload) != expected_keys
    or payload.get("contractName")
    != "chummer.install_linking_postgres_runtime_authority_readiness.v1"
    or payload.get("status") != "pass"
    or payload.get("ready") is not True
    or payload.get("code") != "runtime_role_least_privilege"
    or payload.get("currentRoleMatches") is not True
    or payload.get("leastPrivilegeValid") is not True
    or payload.get("authorityIdentitySha256") != expected_authority
    or payload.get("runtimeRoleSha256") != expected_role
):
    raise SystemExit(1)
checked_at = payload.get("checkedAtUtc")
try:
    parsed = datetime.fromisoformat(
        checked_at.replace("Z", "+00:00")
        if isinstance(checked_at, str)
        else ""
    )
except ValueError:
    raise SystemExit(1)
if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
    raise SystemExit(1)
encoded = (
    json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
).encode("utf-8")
descriptor, temporary_name = tempfile.mkstemp(
    prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
)
temporary = pathlib.Path(temporary_name)
try:
    os.fchmod(descriptor, 0o600)
    written = 0
    while written < len(encoded):
        written += os.write(descriptor, encoded[written:])
    os.fsync(descriptor)
finally:
    os.close(descriptor)
try:
    os.link(temporary, output, follow_symlinks=False)
finally:
    temporary.unlink(missing_ok=True)
metadata = output.lstat()
if (
    not stat.S_ISREG(metadata.st_mode)
    or metadata.st_nlink != 1
    or metadata.st_uid != os.getuid()
    or stat.S_IMODE(metadata.st_mode) != 0o600
):
    raise SystemExit(1)
parent_descriptor = os.open(
    output.parent,
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_CLOEXEC", 0),
)
try:
    os.fsync(parent_descriptor)
finally:
    os.close(parent_descriptor)
print(hashlib.sha256(encoded).hexdigest(), end="")
' "$body_file" "$INSTALL_LINKING_RUNTIME_AUTHORITY_READINESS" \
      "$INSTALL_LINKING_EXPECTED_AUTHORITY_IDENTITY_SHA256" \
      "$INSTALL_LINKING_EXPECTED_RUNTIME_ROLE_SHA256"
  )" || {
    "$TRUSTED_RM" -f -- "$body_file"
    return 1
  }
  "$TRUSTED_RM" -f -- "$body_file"
  [[ "$INSTALL_LINKING_RUNTIME_AUTHORITY_READINESS_SHA256" \
    =~ ^[0-9a-f]{64}$ ]]
}

# This receipt is durable before Docker receives the first instruction that can
# start the migration-enabled candidate. From this boundary forward a failed CLI
# return is an unknown shelf outcome and a blind cutover retry is forbidden.
if ((INITIAL_RELEASE_SHELF_CUTOVER == 1)); then
  trusted_source_python "$CUTOVER_ATTESTOR" request-start \
    --shelf-root "$CANONICAL_RELEASE_SHELF_ROOT" \
    --state-root "$CUTOVER_STATE_ROOT" >/dev/null
fi

if ! start_candidate_portal; then
  abort_portal_recreate "blue-green candidate creation" 1
fi
if ! mark_deploy_phase portal_candidate_started; then
  abort_portal_recreate "candidate start journal" 1
fi

if ! wait_for_candidate_portal_runtime; then
  abort_portal_recreate "candidate readiness" 1
fi

# A migration or recovery candidate is never accepted as the steady deployment.
# First bind the server-owned journal/current/marker result, then recreate the
# candidate under the canonical true/false posture and rerun runtime attestation.
if ((INITIAL_RELEASE_SHELF_CUTOVER == 1 \
  || INITIAL_RELEASE_SHELF_CUTOVER_RECOVERY == 1)); then
  if ! cutover_outcome_json="$(
    trusted_source_python "$CUTOVER_ATTESTOR" verify-outcome \
      --shelf-root "$CANONICAL_RELEASE_SHELF_ROOT" \
      --state-root "$CUTOVER_STATE_ROOT"
  )"; then
    abort_portal_recreate "initial release-shelf outcome verification" 1
  fi
  if ! cutover_classification="$(
    printf '%s' "$cutover_outcome_json" \
      | trusted_source_python -c '
import json, sys
payload = json.load(sys.stdin)
classification = payload.get("classification")
expected_contract = {
    "committed": "chummer.initial-release-shelf-cutover-poststate/v1",
    "aborted": "chummer.initial-release-shelf-cutover-aborted/v1",
}.get(classification)
if payload.get("status") != "pass" or payload.get("contractName") != expected_contract:
    raise SystemExit(1)
print(classification, end="")
'
  )"; then
    abort_portal_recreate "initial release-shelf outcome classification" 1
  fi
  if [[ "$cutover_classification" == aborted ]]; then
    echo "initial_release_shelf_cutover_recovered_aborted; no new migration was started" >&2
    abort_portal_recreate "initial release-shelf recovered abort" 78
  fi
  if ! verify_candidate_publication_readiness; then
    abort_portal_recreate "cutover publication readiness" 1
  fi
  if ! docker_cli container stop "$candidate_portal_container_id" >/dev/null \
    || ! docker_cli container rm "$candidate_portal_container_id" >/dev/null; then
    abort_portal_recreate "cutover candidate retirement" 1
  fi
  candidate_portal_container_id=""
  configure_compose_operation deploy
  if ! compose_cli --profile install-linking-postgres-admin config --format json \
    | trusted_source_python "$SOURCE_ROOT/scripts/validate_public_edge_compose_runtime.py" \
        --operation "$COMPOSE_ATTESTATION_OPERATION" \
        --project-name "$COMPOSE_PROJECT" \
        --source-root "$SOURCE_ROOT" \
        --build-context "$BUILD_CONTEXT" \
        --overlay-root "$OVERLAY_ROOT" \
        --projection-root "$PROJECTION_SNAPSHOT_ROOT" \
        --runtime-proof-bind-source "$RUNTIME_PROOF_BIND_SOURCE" \
        --published-port "$PUBLIC_EDGE_PORT" \
        --output "$STEADY_COMPOSE_ATTESTATION_OUTPUT"; then
    abort_portal_recreate "steady release-shelf Compose attestation" 1
  fi
  FINAL_COMPOSE_ATTESTATION_OUTPUT="$STEADY_COMPOSE_ATTESTATION_OUTPUT"
  if ! trusted_source_python "$CUTOVER_ATTESTOR" snapshot-evidence \
    --kind compose \
    --source "$FINAL_COMPOSE_ATTESTATION_OUTPUT" \
    --output "$FINAL_COMPOSE_ATTESTATION_SNAPSHOT" >/dev/null; then
    abort_portal_recreate "steady Compose evidence snapshot" 1
  fi
  if ! start_candidate_portal; then
    abort_portal_recreate "steady blue-green candidate creation" 1
  fi
  if ! wait_for_candidate_portal_runtime; then
    abort_portal_recreate "steady candidate readiness" 1
  fi
fi

# `/api/ready` is the container healthcheck and covers data-protection custody,
# PostgreSQL install-linking authority, and canonical shelf serving. Publication
# readiness additionally proves layout-v1 activation and the release-storage free-space
# admission gate before a replacement portal can be accepted.
if ((CUTOVER_FINALIZE_REQUIRED == 1)); then
  if ! capture_candidate_publication_readiness; then
    abort_portal_recreate "publication readiness" 1
  fi
elif ! verify_candidate_publication_readiness; then
  abort_portal_recreate "publication readiness" 1
fi

# Re-read the full preflight after portal recreation, then require the runtime
# proof artifact digest to equal the value captured immediately before recreate.
# This closes a path-replacement race at the read-only proof bind boundary.
if ! trusted_source_python "$SOURCE_ROOT/scripts/check_public_edge_deploy_preflight.py" \
  --source-root "$SOURCE_ROOT" \
  --overlay-root "$OVERLAY_ROOT" \
  --public-projection-snapshot-root "$PROJECTION_SNAPSHOT_ROOT" \
  --public-projection-purpose code-deploy \
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256" \
  --runtime-proof-bind-source-sha256 "$RUNTIME_PROOF_BIND_SOURCE_SHA256" \
  --output "$OVERLAY_POSTRECREATE_PREFLIGHT_OUTPUT"; then
  abort_portal_recreate "postrecreate active overlay preflight" 1
fi
if ! runtime_proof_sha256="$(trusted_source_python -c '
import json, re, sys

def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result

def bound_sha(path):
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle, object_pairs_hook=reject_duplicates)
    proof = payload.get("runtimeProofBindSource") or {}
    value = str(proof.get("sha256") or "")
    if (
        payload.get("contractName") != "chummer.public_edge_deploy_preflight.v1"
        or payload.get("status") != "pass"
        or proof.get("status") != "pass"
        or re.fullmatch(r"[0-9a-f]{64}", value) is None
    ):
        raise SystemExit(1)
    return value

before = bound_sha(sys.argv[1])
after = bound_sha(sys.argv[2])
if before != after:
    raise SystemExit(1)
print(before)
' "$OVERLAY_ACTIVE_PREFLIGHT_OUTPUT" "$OVERLAY_POSTRECREATE_PREFLIGHT_OUTPUT")"; then
  abort_portal_recreate "runtime proof bind identity" 1
fi
if [[ "$runtime_proof_sha256" != "$RUNTIME_PROOF_BIND_SOURCE_SHA256" ]]; then
  abort_portal_recreate "runtime proof sealed authority" 1
fi

if ! proof_authority_mount_sha256="$(
  container_proof_sha256_by_id "$candidate_portal_container_id" \
    /proofs/HUB_LOCAL_RELEASE_PROOF.generated.json
)"; then
  abort_portal_recreate "runtime proof authority mount identity" 1
fi
if ! proof_public_mount_sha256="$(
  container_proof_sha256_by_id "$candidate_portal_container_id" \
    /app/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json
)"; then
  abort_portal_recreate "runtime proof public mount identity" 1
fi
if [[ "$proof_authority_mount_sha256" != "$runtime_proof_sha256" \
  || "$proof_public_mount_sha256" != "$runtime_proof_sha256" ]]; then
  abort_portal_recreate "runtime proof mounted-byte identity" 1
fi

verify_candidate_runtime_identity() {
  local candidate_container_image_id candidate_tag_image_id candidate_running networks_json
  candidate_container_image_id="$(docker_cli container inspect --format '{{.Image}}' \
    "$candidate_portal_container_id")" || return 1
  candidate_tag_image_id="$(resolve_image_tag_id "$IMAGE_TAG")" || return 1
  candidate_running="$(docker_cli container inspect --format '{{.State.Running}}' \
    "$candidate_portal_container_id")" || return 1
  networks_json="$(docker_cli container inspect \
    --format '{{json .NetworkSettings.Networks}}' \
    "$candidate_portal_container_id")" || return 1
  trusted_source_python -c '
import json, sys
networks = json.loads(sys.argv[1])
if not isinstance(networks, dict) or not networks:
    raise SystemExit(1)
if not any(
    "chummer-portal" in (network.get("Aliases") or [])
    for network in networks.values()
    if isinstance(network, dict)
):
    raise SystemExit(1)
' "$networks_json" || return 1
  [[ "$candidate_container_image_id" == "$image_id" \
    && "$candidate_tag_image_id" == "$image_id" \
    && "$candidate_running" == true ]]
}

wait_for_exact_container_health() {
  local container_id="$1"
  local health_state
  local -i health_attempt
  for ((health_attempt = 1; health_attempt <= PORTAL_READY_TIMEOUT_SECONDS; health_attempt++)); do
    health_state="$(
      docker_cli container inspect --format \
        '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
        "$container_id"
    )" || return 1
    case "$health_state" in
      healthy) return 0 ;;
      starting) "$TRUSTED_SLEEP" 1 ;;
      unhealthy|none) return 1 ;;
      *) return 1 ;;
    esac
  done
  return 1
}

verify_candidate_tunnel_runtime() {
  local candidate_tunnel_container_id candidate_tunnel_image_id
  local candidate_tunnel_running_state candidate_tunnel_replica_container_id
  local candidate_tunnel_replica_image_id candidate_tunnel_replica_running_state
  candidate_tunnel_container_id="$(
    compose_cli ps --all -q "$CANONICAL_TUNNEL_PRIMARY_SERVICE"
  )" || return 1
  [[ -n "$candidate_tunnel_container_id" && "$candidate_tunnel_container_id" != *$'\n'* ]] || return 1
  if ((prior_tunnel_existed == 1)); then
    [[ "$candidate_tunnel_container_id" == "$prior_tunnel_container_id" ]] || return 1
  fi
  candidate_tunnel_image_id="$(
    docker_cli container inspect --format '{{.Image}}' "$candidate_tunnel_container_id"
  )" || return 1
  candidate_tunnel_running_state="$(
    docker_cli container inspect --format '{{.State.Running}}' "$candidate_tunnel_container_id"
  )" || return 1
  [[ "$candidate_tunnel_image_id" =~ ^sha256:[0-9a-f]{64}$ \
    && "$candidate_tunnel_running_state" == "true" ]] || return 1
  wait_for_exact_container_health "$candidate_tunnel_container_id" || return 1
  if ((prior_tunnel_existed == 1)); then
    [[ "$candidate_tunnel_image_id" == "$prior_tunnel_image_id" ]] || return 1
  fi

  candidate_tunnel_replica_container_id="$(
    compose_cli ps --all -q "$CANONICAL_TUNNEL_REPLICA_SERVICE"
  )" || return 1
  [[ -n "$candidate_tunnel_replica_container_id" \
    && "$candidate_tunnel_replica_container_id" != *$'\n'* \
    && "$candidate_tunnel_replica_container_id" \
      != "$candidate_tunnel_container_id" ]] || return 1
  if ((prior_tunnel_replica_existed == 1)); then
    [[ "$candidate_tunnel_replica_container_id" \
      == "$prior_tunnel_replica_container_id" ]] || return 1
  fi
  candidate_tunnel_replica_image_id="$(
    docker_cli container inspect --format '{{.Image}}' \
      "$candidate_tunnel_replica_container_id"
  )" || return 1
  candidate_tunnel_replica_running_state="$(
    docker_cli container inspect --format '{{.State.Running}}' \
      "$candidate_tunnel_replica_container_id"
  )" || return 1
  [[ "$candidate_tunnel_replica_image_id" =~ ^sha256:[0-9a-f]{64}$ \
    && "$candidate_tunnel_replica_running_state" == "true" ]] || return 1
  wait_for_exact_container_health \
    "$candidate_tunnel_replica_container_id" || return 1
  if ((prior_tunnel_replica_existed == 1)); then
    [[ "$candidate_tunnel_replica_image_id" \
      == "$prior_tunnel_replica_image_id" ]] || return 1
  fi
}

if ! verify_candidate_runtime_identity; then
  abort_portal_recreate "candidate image identity" 1
fi
if ! capture_candidate_install_linking_authority_readiness; then
  abort_portal_recreate "InstallLinking runtime authority readiness" 1
fi

if ((prior_tunnel_existed == 1)); then
  if ! docker_cli start "$prior_tunnel_container_id" >/dev/null \
    || [[ "$(docker_cli container inspect --format '{{.State.Running}}' "$prior_tunnel_container_id")" != "true" ]]; then
    abort_portal_recreate "tunnel restart" 1
  fi
else
  if ! compose_cli up -d --no-build --no-deps \
    "$CANONICAL_TUNNEL_PRIMARY_SERVICE"; then
    abort_portal_recreate "primary tunnel creation" 1
  fi
fi
if ((prior_tunnel_replica_existed == 1)); then
  if ! docker_cli start "$prior_tunnel_replica_container_id" >/dev/null \
    || [[ "$(
      docker_cli container inspect --format '{{.State.Running}}' \
        "$prior_tunnel_replica_container_id"
    )" != "true" ]]; then
    abort_portal_recreate "tunnel replica restart" 1
  fi
else
  if ! compose_cli up -d --no-build --no-deps \
    "$CANONICAL_TUNNEL_REPLICA_SERVICE"; then
    abort_portal_recreate "tunnel replica creation" 1
  fi
fi
if ! verify_candidate_tunnel_runtime; then
  abort_portal_recreate "both candidate tunnel identities" 1
fi
if ! mark_deploy_phase tunnel_started; then
  abort_portal_recreate "both tunnel restarts journal" 1
fi

postdeploy_command=(
  trusted_source_python "$SOURCE_ROOT/scripts/verify_public_edge_postdeploy_gate.py"
  --base-url "$BASE_URL"
  --strict-preflight
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT"
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256"
  --public-release-manifest "$CANONICAL_RELEASE_SHELF_ROOT/RELEASE_CHANNEL.generated.json"
  --public-projection-snapshot-root "$PROJECTION_SNAPSHOT_ROOT"
  --public-projection-purpose code-deploy
  --expect-code-deploy-review-required
  --runtime-proof-bind-source-sha256 "$RUNTIME_PROOF_BIND_SOURCE_SHA256"
  --overlay-root "$OVERLAY_ROOT"
  --expected-build-info "$OVERLAY_ROOT/.codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
  --require-downloads-status-playwright
  --require-mobile-pwa-viewport-playwright
  --require-frontdoor-navigation-playwright
  --playwright-artifact-dir "$PLAYWRIGHT_ARTIFACT_DIR/downloads-status"
  --mobile-pwa-viewport-artifact-dir "$PLAYWRIGHT_ARTIFACT_DIR/mobile-pwa-viewport"
  --frontdoor-navigation-artifact-dir "$PLAYWRIGHT_ARTIFACT_DIR/frontdoor-navigation"
  --playwright-authority "$PLAYWRIGHT_AUTHORITY"
  --playwright-authority-sha256 "$PLAYWRIGHT_AUTHORITY_SHA256"
  --playwright-host-build-root "$PUBLIC_EDGE_HOST_BUILD_ROOT"
  --output "$POSTDEPLOY_OUTPUT"
)

for ((attempt = 1; attempt <= POSTDEPLOY_ATTEMPTS; attempt++)); do
  if "${postdeploy_command[@]}"; then
    if ((CUTOVER_FINALIZE_REQUIRED == 1)); then
      if ! trusted_source_python "$CUTOVER_ATTESTOR" snapshot-evidence \
        --kind postdeploy \
        --source "$POSTDEPLOY_OUTPUT" \
        --output "$FINAL_POSTDEPLOY_ATTESTATION_SNAPSHOT" >/dev/null; then
        abort_portal_recreate "postdeploy evidence snapshot" 1
      fi
      FINAL_POSTDEPLOY_ATTESTATION_OUTPUT="$FINAL_POSTDEPLOY_ATTESTATION_SNAPSHOT"
    fi
    break
  fi
  if ((attempt == POSTDEPLOY_ATTEMPTS)); then
    exit 1
  fi
  "$TRUSTED_SLEEP" "$POSTDEPLOY_RETRY_DELAY_SECONDS"
done

if ! trusted_source_python -c '
import json, pathlib, re, sys
from urllib.parse import unquote
# Public-edge postdeploy code-deploy receipt scanner.
payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
secret_key_stems = (
    "accesskey", "accountkey", "apikey", "authorization", "bearertoken",
    "clientsecret", "connstr", "connectionstring", "connectionuri", "connectionurl",
    "credential", "databaseurl", "dsn", "password", "passwd", "privatekey",
    "pwd", "secret", "sharedaccesssignature", "token",
)
secret_key_short_words = {"connstr", "dsn", "dsns", "pwd", "pwds", "sas"}
safe_boolean_suffixes = {
    "absent", "capable", "configured", "exposed", "leaked", "matches", "performed",
    "present", "redacted", "required", "stored", "valid",
}
safe_integer_suffixes = {"count", "device", "inode", "mtimens"}
safe_digest_suffixes = {"digest", "hash", "sha256"}
def key_parts(value):
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    words = re.sub(r"[^A-Za-z0-9]+", "_", words).strip("_").lower()
    return tuple(part for part in words.split("_") if part)
def secret_like_key(value):
    parts = key_parts(value)
    collapsed = "".join(parts)
    return bool(
        parts
        and (
            any(stem in collapsed for stem in secret_key_stems)
            or any(part in secret_key_short_words for part in parts)
        )
    )
def safe_secret_metadata(key, value):
    parts = key_parts(key)
    if not parts or not secret_like_key(key):
        return False
    suffix = parts[-1]
    if suffix in safe_boolean_suffixes:
        return type(value) is bool
    if suffix in safe_integer_suffixes:
        return type(value) is int and value >= 0
    if suffix in safe_digest_suffixes:
        return bool(
            isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value) is not None
        )
    if key.startswith("/run/chummer-secrets/"):
        return bool(
            isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value) is not None
        )
    return False
def secret_like_value(value):
    if not isinstance(value, str):
        return False
    for candidate in {value, unquote(value)}:
        if (
            re.search(
                r"(?i)(?:passwords?|passwds?|pwds?|tokens?|secrets?|"
                r"credentials?|accountkeys?|api[_ -]?keys?|client[_ -]?secrets?|"
                r"private[_ -]?keys?|authorization|connection[_ -]?strings?|"
                r"dsns?)\s*[:=]",
                candidate,
            )
            or re.search(r"://[^/\s:@]+:[^@\s/]+@", candidate)
            or re.search(r"(?i)\bpostgres(?:ql)?://", candidate)
            or re.search(
                r"(?i)[?&](?:access_token|api[_-]?key|password|sig|signature|token)=",
                candidate,
            )
            or re.search(
                r"(?i)-----BEGIN [A-Z0-9 ]+(?:PRIVATE KEY|CERTIFICATE)-----",
                candidate,
            )
            or re.search(r"(?i)\bAccountKey\s*=", candidate)
            or re.search(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", candidate)
            or re.search(
                r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|"
                r"github_pat_[A-Za-z0-9_]{20,}|"
                r"(?:AKIA|ASIA)[0-9A-Z]{16}|"
                r"(?:sk|rk)_live_[A-Za-z0-9]{16,}|"
                r"xox[baprs]-[A-Za-z0-9-]{10,}|"
                r"AIza[0-9A-Za-z_-]{20,})\b",
                candidate,
            )
            or re.search(
                r"\beyJ[A-Za-z0-9_-]{8,}\."
                r"[A-Za-z0-9_-]{8,}\."
                r"[A-Za-z0-9_-]{8,}\b",
                candidate,
            )
        ):
            return True
    return False
def has_secret_material(value):
    if isinstance(value, dict):
        return any(
            not isinstance(key, str)
            or (
                secret_like_key(key)
                and not safe_secret_metadata(key, item)
            )
            or has_secret_material(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(has_secret_material(item) for item in value)
    return secret_like_value(value)
if (
    payload.get("contractName") != "chummer.public_edge_postdeploy_gate.v2"
    or payload.get("status") != "pass"
    or payload.get("projectionPurpose") != "code-deploy"
    or payload.get("projectionStatus") != "review_required"
    or payload.get("projectionStage") != "code_deploy_review_required"
    or payload.get("codeDeploymentAuthority") is not True
    or payload.get("releaseUploadAuthority") is not False
    or payload.get("releaseReady") is not False
    or payload.get("codeDeployReviewRequiredAuthoritySatisfied") is not True
    or ("childReceipts" in payload and payload.get("childReceipts") != {})
    or has_secret_material(payload)
):
    raise SystemExit(1)
' "$FINAL_POSTDEPLOY_ATTESTATION_OUTPUT"; then
  abort_portal_recreate "postdeploy code-deploy authority" 1
fi

if ! verify_candidate_runtime_identity; then
  abort_portal_recreate "postdeploy image identity" 1
fi
if ! verify_candidate_tunnel_runtime; then
  abort_portal_recreate "postdeploy tunnel identity" 1
fi
if ! docker_cli container update --restart unless-stopped \
  "$candidate_portal_container_id" >/dev/null; then
  abort_portal_recreate "candidate restart policy" 1
fi

if ((INITIAL_RELEASE_SHELF_CUTOVER == 1 \
  || INITIAL_RELEASE_SHELF_CUTOVER_RECOVERY == 1 \
  || CUTOVER_STEADY_HANDOFF == 1)); then
  if ! cutover_final_poststate="$(
    trusted_source_python "$CUTOVER_ATTESTOR" verify-handoff \
      --shelf-root "$CANONICAL_RELEASE_SHELF_ROOT" \
      --state-root "$CUTOVER_STATE_ROOT"
  )"; then
    abort_portal_recreate "final initial release-shelf poststate" 1
  fi
  if ! cutover_final_classification="$(
    printf '%s' "$cutover_final_poststate" \
      | trusted_source_python -c '
import json, sys
payload = json.load(sys.stdin)
if (
    payload.get("contractName")
    != "chummer.initial-release-shelf-cutover-poststate/v1"
    or payload.get("status") != "pass"
    or payload.get("classification") != "committed"
):
    raise SystemExit(1)
print("committed", end="")
'
  )" || [[ "$cutover_final_classification" != committed ]]; then
    abort_portal_recreate "final initial release-shelf committed classification" 1
  fi
fi

if ! precompletion_boundary_verification="$(
  verify_install_linking_cutover_boundary \
    "$INSTALL_LINKING_CUTOVER_BOUNDARY_SHA256" \
    validate_completed \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID"
)" \
  || [[ "$precompletion_boundary_verification" \
    != "$install_linking_boundary_verification" ]]; then
  abort_portal_recreate "precompletion InstallLinking boundary identity" 1
fi
if ! precompletion_portal_tag_id="$(resolve_exact_image_id "$IMAGE_TAG")" \
  || ! precompletion_tool_tag_id="$(resolve_exact_image_id "$TOOL_IMAGE_TAG")" \
  || ! precompletion_candidate_portal_id="$(
    resolve_exact_image_id "$INSTALL_LINKING_CANDIDATE_PORTAL_TAG"
  )" \
  || ! precompletion_candidate_tool_id="$(
    resolve_exact_image_id "$INSTALL_LINKING_CANDIDATE_TOOL_TAG"
  )" \
  || [[ "$precompletion_portal_tag_id" \
      != "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
    || "$precompletion_candidate_portal_id" != "$precompletion_portal_tag_id" \
    || "$precompletion_tool_tag_id" \
      != "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
    || "$precompletion_candidate_tool_id" != "$precompletion_tool_tag_id" ]]; then
  abort_portal_recreate "precompletion candidate image identity" 1
fi
if ! precompletion_transaction_backup_sha256="$(
  publish_private_snapshot \
    "$OVERLAY_PRIOR_STATE_OUTPUT" \
    "$PRECOMPLETION_TRANSACTION_BACKUP" \
    raw \
    1
)" \
  || [[ ! "$precompletion_transaction_backup_sha256" =~ ^[0-9a-f]{64}$ ]]; then
  abort_portal_recreate "precompletion transaction backup" 1
fi
precompletion_transaction_backup_active=1

if ! trusted_source_python "$SOURCE_ROOT/scripts/public_edge_overlay_transaction.py" complete \
  --source-root "$SOURCE_ROOT" \
  --active-root "$OVERLAY_ROOT" \
  --output "$OVERLAY_PRIOR_STATE_OUTPUT" \
  --runtime-authority-output "$CANONICAL_ACTIVE_RUNTIME_AUTHORITY" \
  --candidate-portal-container-id "$candidate_portal_container_id" \
  --candidate-portal-container-name "$CANDIDATE_PORTAL_CONTAINER_NAME" \
  --candidate-portal-image-id "$image_id" \
  --install-linking-authority-readiness \
    "$INSTALL_LINKING_RUNTIME_AUTHORITY_READINESS" \
  --install-linking-authority-readiness-sha256 \
    "$INSTALL_LINKING_RUNTIME_AUTHORITY_READINESS_SHA256" \
  --shared-mutation-lock-token "$deploy_lock_owner_token"; then
  abort_portal_recreate "completed deployment journal retirement" 70
fi
if ((CUTOVER_FINALIZE_REQUIRED == 1)); then
  if ! trusted_source_python "$CUTOVER_ATTESTOR" snapshot-evidence \
    --kind active-runtime \
    --source "$CANONICAL_ACTIVE_RUNTIME_AUTHORITY" \
    --output "$ACTIVE_RUNTIME_AUTHORITY_SNAPSHOT" >/dev/null; then
    echo "steady public edge is deployed, but active runtime evidence snapshot failed; inspect before retry" >&2
    exit 70
  fi
fi
if ((CUTOVER_FINALIZE_REQUIRED == 1)); then
  if ! trusted_source_python "$CUTOVER_ATTESTOR" finalize \
    --state-root "$CUTOVER_STATE_ROOT" \
    --compose-attestation "$FINAL_COMPOSE_ATTESTATION_SNAPSHOT" \
    --publication-readiness-attestation "$PUBLICATION_READINESS_ATTESTATION" \
    --postdeploy-attestation "$FINAL_POSTDEPLOY_ATTESTATION_SNAPSHOT" \
    --active-runtime-authority "$ACTIVE_RUNTIME_AUTHORITY_SNAPSHOT" \
    --candidate-image-id "$image_id" >/dev/null; then
    echo "steady public edge is deployed, but cutover completion receipt failed; inspect before retry" >&2
    exit 70
  fi
fi

if ! INSTALL_LINKING_PRIVATE_POSTDEPLOY_RECEIPT_SHA256="$(
  publish_private_snapshot \
    "$FINAL_POSTDEPLOY_ATTESTATION_OUTPUT" \
    "$INSTALL_LINKING_PRIVATE_POSTDEPLOY_RECEIPT" \
    canonical-json \
    0
)" \
  || [[ ! "$INSTALL_LINKING_PRIVATE_POSTDEPLOY_RECEIPT_SHA256" \
    =~ ^[0-9a-f]{64}$ ]]; then
  abort_portal_recreate "private postdeploy acceptance receipt" 1
fi
if ! INSTALL_LINKING_PRIVATE_ACTIVE_RUNTIME_RECEIPT_SHA256="$(
  publish_private_snapshot \
    "$CANONICAL_ACTIVE_RUNTIME_AUTHORITY" \
    "$INSTALL_LINKING_PRIVATE_ACTIVE_RUNTIME_RECEIPT" \
    canonical-json \
    1
)" \
  || [[ ! "$INSTALL_LINKING_PRIVATE_ACTIVE_RUNTIME_RECEIPT_SHA256" \
    =~ ^[0-9a-f]{64}$ ]]; then
  abort_portal_recreate "private active-runtime acceptance receipt" 1
fi
if ! INSTALL_LINKING_PUBLIC_ACCEPTANCE_EVIDENCE_SHA256="$(
  write_install_linking_public_acceptance_evidence
)" \
  || [[ ! "$INSTALL_LINKING_PUBLIC_ACCEPTANCE_EVIDENCE_SHA256" \
    =~ ^[0-9a-f]{64}$ ]]; then
  abort_portal_recreate "InstallLinking public acceptance evidence" 1
fi
if ! verified_public_acceptance_evidence_sha256="$(
  trusted_source_python -c '
# InstallLinking public acceptance evidence precommit verifier.
import pathlib, sys
scripts = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(scripts))
from materialize_install_linking_cutover_boundary import (
    bind_active_build_info,
    bind_phase_evidence,
)

build_path, build_sha256, build_info = bind_active_build_info(
    pathlib.Path(sys.argv[3]),
    cutover_id=sys.argv[4],
    candidate_image_id=sys.argv[5],
    candidate_tool_image_id=sys.argv[6],
)
if str(build_path) != sys.argv[3] or build_sha256 != sys.argv[7]:
    raise SystemExit(1)
evidence_path, evidence_sha256, _ = bind_phase_evidence(
    pathlib.Path(sys.argv[2]),
    phase="public_acceptance_completed",
    cutover_id=sys.argv[4],
    candidate_image_id=sys.argv[5],
    candidate_tool_image_id=sys.argv[6],
    candidate_build_info_sha256=build_sha256,
    candidate_build_info=build_info,
    boundary_output=pathlib.Path(sys.argv[8]),
)
if str(evidence_path) != sys.argv[2]:
    raise SystemExit(1)
print(evidence_sha256, end="")
' "$SOURCE_ROOT/scripts" "$INSTALL_LINKING_PUBLIC_ACCEPTANCE_EVIDENCE" \
    "$INSTALL_LINKING_ACTIVE_BUILD_INFO" "$INSTALL_LINKING_CUTOVER_ID" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
    "$INSTALL_LINKING_ACTIVE_BUILD_INFO_SHA256" \
    "$INSTALL_LINKING_CUTOVER_BOUNDARY"
)"; then
  abort_portal_recreate "InstallLinking public acceptance evidence verification" 1
fi
if [[ "$verified_public_acceptance_evidence_sha256" \
  != "$INSTALL_LINKING_PUBLIC_ACCEPTANCE_EVIDENCE_SHA256" ]]; then
  abort_portal_recreate "InstallLinking public acceptance evidence digest" 1
fi

install_linking_materializer_status=0
install_linking_materializer_invoked=1
trusted_source_python "$INSTALL_LINKING_CUTOVER_MATERIALIZER" \
  --output "$INSTALL_LINKING_CUTOVER_BOUNDARY" \
  --phase public_acceptance_completed \
  --cutover-id "$INSTALL_LINKING_CUTOVER_ID" \
  --candidate-image-id "$EXPECTED_INSTALL_LINKING_CANDIDATE_IMAGE_ID" \
  --candidate-tool-image-id \
    "$EXPECTED_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID" \
  --active-build-info "$INSTALL_LINKING_ACTIVE_BUILD_INFO" \
  --evidence-receipt "$INSTALL_LINKING_PUBLIC_ACCEPTANCE_EVIDENCE" \
  >/dev/null || install_linking_materializer_status=$?
if ! accepted_install_linking_boundary_sha256="$(
  verify_install_linking_public_acceptance_boundary
)"; then
  abort_portal_recreate \
    "InstallLinking public acceptance materializer exact reconciliation" \
    70
fi

# The exact boundary is now independently re-read and verified as an accepted,
# irreversible receipt. A nonzero materializer exit can therefore be reconciled
# without rolling the live candidate back behind its passing acceptance chain.
deployment_transaction_active=0
precompletion_transaction_backup_active=0
if ((install_linking_materializer_status != 0)); then
  printf \
    'install_linking_public_acceptance_materializer_reconciled exit_status=%s boundary_sha256=%s\n' \
    "$install_linking_materializer_status" \
    "$accepted_install_linking_boundary_sha256" >&2
fi

if ((prior_portal_existed == 1)) \
  && [[ "$prior_portal_container_id" != "$candidate_portal_container_id" ]]; then
  prior_portal_postcommit_running="$(
    docker_cli container inspect --format '{{.State.Running}}' \
      "$prior_portal_container_id"
  )" || prior_portal_postcommit_running=unknown
  if [[ "$prior_portal_postcommit_running" == false ]]; then
    if ! docker_cli container rm "$prior_portal_container_id" >/dev/null; then
      printf 'public_edge_prior_portal_cleanup_retained %s\n' \
        "$prior_portal_container_id" >&2
    fi
  else
    printf 'public_edge_prior_portal_cleanup_retained %s\n' \
      "$prior_portal_container_id" >&2
  fi
fi
if ((RELEASE_UPLOAD_TICKET_EPOCH_ROTATION == 1)); then
  epoch_rotation_status=0
  # From this point an interrupt must retain the authenticated mutation lease.
  # The child is the only authority that can distinguish a safe precommit
  # refusal from an already-crossed credential boundary.
  epoch_rotation_fail_forward_required=1
  printf '%s\n' "$deploy_lock_owner_token" \
    | trusted_source_python \
      "$SOURCE_ROOT/scripts/rotate_release_upload_ticket_epoch.py" \
    --env-file "$ENV_FILE" \
    --active-runtime-authority "$CANONICAL_ACTIVE_RUNTIME_AUTHORITY" \
    --epoch-authority-output \
      "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_AUTHORITY" \
    --epoch-history-path \
      "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
    --expected-epoch-history-sha256 \
      "$RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_EXPECTED_SHA256" \
    --epoch-history-bootstrap-authority \
      "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_AUTHORITY_INPUT" \
    --expected-epoch-history-bootstrap-authority-sha256 \
      "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_AUTHORITY_SHA256" \
    --epoch-history-bootstrap-marker \
      "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" \
    --expected-epoch-history-bootstrap-marker-sha256 \
      "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_EXPECTED_SHA256" \
    --edge-waf-local-evidence-source \
      "$RELEASE_UPLOAD_TICKET_EDGE_WAF_LOCAL_EVIDENCE_SOURCE_INPUT" \
    --expected-edge-waf-local-evidence-sha256 \
      "$RELEASE_UPLOAD_TICKET_EDGE_WAF_LOCAL_EVIDENCE_SOURCE_SHA256" \
    --output "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" \
    --expected-env-sha256-before "$INSTALL_LINKING_ENV_SHA256" \
    --expected-image-id "$image_id" \
    --expected-proof-sha256 "$RUNTIME_PROOF_BIND_SOURCE_SHA256" \
    --image-tag "$IMAGE_TAG" \
    --expected-source-head "${EXPECTED_HEAD,,}" \
    --new-epoch "$RELEASE_UPLOAD_TICKET_NEXT_EPOCH" \
    --expected-portal-replicas 1 \
    --shared-mutation-lock-fd 0 \
    --docker-config-root "$CANONICAL_DOCKER_CONFIG_ROOT" \
    --docker-context "$CANONICAL_DOCKER_CONTEXT" \
    --compose-file "$COMPOSE_SOURCE_SNAPSHOT" \
    --project-name "$COMPOSE_PROJECT" \
    --source-root "$SOURCE_ROOT" \
    --build-context "$BUILD_CONTEXT" \
    --overlay-root "$OVERLAY_ROOT" \
    --projection-root "$PROJECTION_SNAPSHOT_ROOT" \
    --proof-bind-source "$RUNTIME_PROOF_BIND_SOURCE" \
    --published-port "$PUBLIC_EDGE_PORT" \
    --base-url "$BASE_URL" \
    --old-ticket-path "$RELEASE_UPLOAD_OLD_TICKET_PATH" \
    --old-ticket-authority-fd 3 \
    3<"$RELEASE_UPLOAD_OLD_TICKET_AUTHORITY_INPUT" \
    >/dev/null \
    || epoch_rotation_status=$?
  RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_OBSERVED_SHA256="$(
    capture_release_upload_ticket_epoch_history_sha256
  )" || exit 76
  RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_OBSERVED_SHA256="$(
    capture_release_upload_ticket_epoch_bootstrap_marker_sha256
  )" || exit 76
  case "$epoch_rotation_status" in
    0)
      RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256="$(
        "$TRUSTED_SHA256SUM" -- "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT"
      )" || exit 70
      RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256="${RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256%% *}"
      if [[ ! "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256" \
        =~ ^[0-9a-f]{64}$ ]]; then
        exit 70
      fi
      epoch_rotation_fail_forward_required=0
      ;;
    76)
      printf \
        'release_upload_ticket_epoch_fail_forward_required receipt=%s history=%s history_sha256=%s bootstrap_marker=%s bootstrap_marker_sha256=%s\n' \
        "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" \
        "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
        "$RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_OBSERVED_SHA256" \
        "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" \
        "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_OBSERVED_SHA256" >&2
      exit 76
      ;;
    75)
      epoch_rotation_fail_forward_required=0
      epoch_rotation_precommit_refused=1
      ;;
    *)
      printf \
        'release-upload ticket epoch rotation outcome requires authenticated fail-forward resume; receipt=%s history=%s history_sha256=%s bootstrap_marker=%s bootstrap_marker_sha256=%s\n' \
        "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" \
        "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
        "$RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_OBSERVED_SHA256" \
        "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" \
        "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_OBSERVED_SHA256" >&2
      exit "$epoch_rotation_status"
      ;;
  esac
fi
if ! release_deploy_lock; then
  echo "failed to release public edge deployment lock" >&2
  exit 70
fi
trap - EXIT HUP INT TERM

if ((RELEASE_UPLOAD_TICKET_EPOCH_ROTATION == 1 \
  && epoch_rotation_precommit_refused == 1)); then
  printf \
    'release_upload_ticket_epoch_refused_before_commit receipt=%s history=%s history_sha256=%s bootstrap_marker=%s bootstrap_marker_sha256=%s\n' \
    "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" \
    "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
    "$RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_OBSERVED_SHA256" \
    "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" \
    "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_OBSERVED_SHA256" >&2
  exit 75
fi
if ((RELEASE_UPLOAD_TICKET_EPOCH_ROTATION == 1)); then
  printf \
    'release_upload_ticket_epoch_rotated receipt=%s receipt_sha256=%s history=%s history_sha256=%s bootstrap_marker=%s bootstrap_marker_sha256=%s\n' \
    "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT" \
    "$RELEASE_UPLOAD_TICKET_EPOCH_RECEIPT_SHA256" \
    "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_HISTORY" \
    "$RELEASE_UPLOAD_TICKET_EPOCH_HISTORY_OBSERVED_SHA256" \
    "$CANONICAL_RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER" \
    "$RELEASE_UPLOAD_TICKET_EPOCH_BOOTSTRAP_MARKER_OBSERVED_SHA256"
fi
printf 'public_edge_portal_deployed %s\n' "$image_id"
