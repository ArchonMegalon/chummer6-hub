#!/usr/bin/bash
set -euo pipefail

# Required outer boundary (with the explicit CHUMMER authority/runtime inputs
# inserted before the executable):
# /usr/bin/env -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
#   CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1 ... \
#   /usr/bin/bash --noprofile --norc scripts/deploy_public_edge_portal.sh
if [[ "${CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH-}" != "1" ]]; then
  printf '%s\n' \
    'public edge deploy requires /usr/bin/env -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1 ... /usr/bin/bash --noprofile --norc' >&2
  exit 2
fi

DEPLOY_OPERATION="${1:-deploy}"
if (($# > 1)); then
  echo "usage: deploy_public_edge_portal.sh [deploy|recover]" >&2
  exit 2
fi
case "$DEPLOY_OPERATION" in
  deploy|recover) ;;
  *) echo "usage: deploy_public_edge_portal.sh [deploy|recover]" >&2; exit 2 ;;
esac

readonly TRUSTED_GIT="/usr/bin/git"
readonly TRUSTED_PYTHON="/usr/bin/python3"
readonly TRUSTED_DOCKER="/usr/bin/docker"
readonly TRUSTED_CURL="/usr/bin/curl"
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

for trusted_tool in \
  "$TRUSTED_GIT" "$TRUSTED_PYTHON" "$TRUSTED_DOCKER" "$TRUSTED_CURL" \
  "$TRUSTED_TIMEOUT" "$TRUSTED_REALPATH" "$TRUSTED_INSTALL" "$TRUSTED_CHMOD" \
  "$TRUSTED_MKDIR" "$TRUSTED_RMDIR" "$TRUSTED_AWK" "$TRUSTED_SLEEP" \
  "$TRUSTED_ENV" "$TRUSTED_DIRNAME" "$TRUSTED_STAT" "$TRUSTED_SHA256SUM" \
  "$TRUSTED_MKTEMP" "$TRUSTED_RM"; do
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
    BASH_ENV|ENV|CDPATH|GLOBIGNORE|LD_PRELOAD|LD_LIBRARY_PATH|PYTHONHOME|PYTHONPATH|PYTHONSTARTUP|PYTHONINSPECT|PYTHONBREAKPOINT|PYTHONWARNINGS|PYTHONSAFEPATH|DOCKER_*|BUILDKIT_HOST|BUILDX_*|COMPOSE_*)
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
CANONICAL_ENV_FILE="/docker/chummercomplete/chummer.run-services/.env"
CANONICAL_IMAGE_TAG="chummer-run-api:local"
CANONICAL_OVERLAY_ROOT="/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app"
CANONICAL_PUBLIC_EDGE_PORT="8091"
CANONICAL_BASE_URL="https://chummer.run"
CANONICAL_DOCKER_CONTEXT="default"
CANONICAL_DOCKER_HOST="unix:///var/run/docker.sock"
CANONICAL_BUILDX_BUILDER="default"
CANONICAL_DOCKER_CONFIG_ROOT="/docker/chummercomplete/.state/public-edge-docker-cli"
CANONICAL_FLEET_MEDIA_CONTRACTS="/docker/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts"
CANONICAL_DESIGN_PRODUCT_ROOT="/docker/chummercomplete/chummer-design"
CANONICAL_RELEASE_CHANNEL_RECEIPT="/docker/chummercomplete/chummer-hub-registry/.codex-studio/published/RELEASE_CHANNEL.generated.json"
CANONICAL_RUNTIME_PROOF_BIND_SOURCE="/docker/chummercomplete/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
BUILD_CONTEXT="${CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT:-$CANONICAL_BUILD_CONTEXT}"
COMPOSE_FILE_INPUT="${CHUMMER_PUBLIC_EDGE_COMPOSE_FILE:-$ROOT_DIR/docker-compose.public-edge.yml}"
COMPOSE_PROJECT="${CHUMMER_PUBLIC_EDGE_PROJECT_NAME:-$CANONICAL_COMPOSE_PROJECT}"
ENV_FILE_INPUT="${CHUMMER_PUBLIC_EDGE_ENV_FILE:-$CANONICAL_ENV_FILE}"
IMAGE_TAG="${CHUMMER_PUBLIC_EDGE_PORTAL_IMAGE_TAG:-$CANONICAL_IMAGE_TAG}"
OVERLAY_ROOT="${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR:-$CANONICAL_OVERLAY_ROOT}"
BASE_URL="${CHUMMER_PUBLIC_EDGE_BASE_URL:-$CANONICAL_BASE_URL}"
RELEASE_CHANNEL_RECEIPT_INPUT="${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT-}"
RELEASE_CHANNEL_RECEIPT_SHA256="${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256-}"
RUNTIME_PROOF_BIND_SOURCE_SHA256="${CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256-}"
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
DEPLOY_LOCK_ROOT="/docker/chummercomplete/.state"
DEPLOY_LOCK_DIR="$DEPLOY_LOCK_ROOT/public-edge-mutation.lock"
CANONICAL_DEPLOY_LOCK_AUTH_ROOT="$DEPLOY_LOCK_ROOT/public-edge-lock-recovery-receipts"
CANONICAL_DEPLOY_RECEIPT_ROOT="$DEPLOY_LOCK_ROOT/public-edge-deploy-receipts"
CANONICAL_ACTIVE_RUNTIME_AUTHORITY="$CANONICAL_DEPLOY_RECEIPT_ROOT/active-runtime-authority.json"

if [[ "$COMPOSE_FILE_INPUT" != /* ]]; then
  COMPOSE_FILE_INPUT="$SOURCE_ROOT/$COMPOSE_FILE_INPUT"
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
if [[ ! "$RUNTIME_PROOF_BIND_SOURCE_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256 must be externally supplied as a lowercase SHA-256" >&2
  exit 2
fi
RECOVERY_ROUTE_REQUESTED=0
if [[ "$DEPLOY_OPERATION" == recover \
  || -e "$CANONICAL_DEPLOY_RECEIPT_ROOT/active-overlay-transaction.json" \
  || -L "$CANONICAL_DEPLOY_RECEIPT_ROOT/active-overlay-transaction.json" ]]; then
  RECOVERY_ROUTE_REQUESTED=1
fi
RELEASE_CHANNEL_RECEIPT=""
if ((RECOVERY_ROUTE_REQUESTED == 0)); then
  if [[ -z "$RELEASE_CHANNEL_RECEIPT_INPUT" ]]; then
    echo "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT must be externally supplied" >&2
    exit 2
  fi
  if ! RELEASE_CHANNEL_RECEIPT="$("$TRUSTED_REALPATH" -e -- "$RELEASE_CHANNEL_RECEIPT_INPUT")"; then
    echo "public edge release-channel receipt is missing: $RELEASE_CHANNEL_RECEIPT_INPUT" >&2
    exit 2
  fi
  if [[ "$RELEASE_CHANNEL_RECEIPT" != "$CANONICAL_RELEASE_CHANNEL_RECEIPT" ]]; then
    echo "public edge deploy refuses a non-canonical release-channel receipt" >&2
    exit 2
  fi
  if [[ ! "$RELEASE_CHANNEL_RECEIPT_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
    echo "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256 must be independently supplied as a lowercase SHA-256" >&2
    exit 2
  fi
  actual_release_channel_receipt_sha256="$(
    "$TRUSTED_SHA256SUM" -- "$RELEASE_CHANNEL_RECEIPT"
  )"
  actual_release_channel_receipt_sha256="${actual_release_channel_receipt_sha256%% *}"
  if [[ "$actual_release_channel_receipt_sha256" != "$RELEASE_CHANNEL_RECEIPT_SHA256" ]]; then
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
if deploy_lock_metadata="$(
  "$TRUSTED_ENV" -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
    "$TRUSTED_PYTHON" -I -c '
import ctypes, errno, hashlib, os, secrets, stat, sys
lock_root = os.fsencode(sys.argv[1])
lock_path = os.fsencode(sys.argv[2])
authorization_root = os.fsencode(sys.argv[3])
lock_root_stat = os.lstat(lock_root)
authorization_root_stat = os.lstat(authorization_root)
for metadata in (lock_root_stat, authorization_root_stat):
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise SystemExit(70)
token = secrets.token_hex(32)
token_digest = hashlib.sha256(token.encode("ascii")).hexdigest()
staging_path = os.path.join(
    lock_root, f".public-edge-mutation.lock.staging.{token[:24]}".encode("ascii")
)
authorization_path = os.path.join(
    authorization_root, f"deploy-{token_digest}.owner-token".encode("ascii")
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
    raise SystemExit(70)
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
AT_FDCWD = -100
RENAME_NOREPLACE = 1
if renameat2(AT_FDCWD, staging_path, AT_FDCWD, lock_path, RENAME_NOREPLACE) != 0:
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        current_staging = os.lstat(staging_path)
        current_token = os.lstat(token_path)
        current_authorization = os.lstat(authorization_path)
        if (
            (current_staging.st_dev, current_staging.st_ino)
            != (staging_stat.st_dev, staging_stat.st_ino)
            or (current_token.st_dev, current_token.st_ino)
            != (token_stat.st_dev, token_stat.st_ino)
            or (current_authorization.st_dev, current_authorization.st_ino)
            != (authorization_stat.st_dev, authorization_stat.st_ino)
        ):
            raise SystemExit(70)
        os.unlink(token_path)
        os.rmdir(staging_path)
        os.unlink(authorization_path)
        for path in (lock_root, authorization_root):
            directory_descriptor = os.open(
                path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            )
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        raise SystemExit(75)
    raise OSError(error_number, os.strerror(error_number), os.fsdecode(lock_path))
lock_root_descriptor = os.open(
    lock_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
)
try:
    os.fsync(lock_root_descriptor)
finally:
    os.close(lock_root_descriptor)
lock_stat = os.lstat(lock_path)
published_token_path = os.path.join(lock_path, b"owner-token")
published_token_stat = os.lstat(published_token_path)
if (
    (lock_stat.st_dev, lock_stat.st_ino) != (staging_stat.st_dev, staging_stat.st_ino)
    or (published_token_stat.st_dev, published_token_stat.st_ino)
    != (token_stat.st_dev, token_stat.st_ino)
):
    raise SystemExit(70)
print(
    f"{token}|{lock_stat.st_dev}:{lock_stat.st_ino}|"
    f"{token_stat.st_dev}:{token_stat.st_ino}|"
    f"{authorization_stat.st_dev}:{authorization_stat.st_ino}|"
    f"{os.fsdecode(authorization_path)}"
)
' "$DEPLOY_LOCK_ROOT" "$DEPLOY_LOCK_DIR" "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT"
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
  <<<"$deploy_lock_metadata"
deploy_lock_token_digest="$(
  printf '%s' "$deploy_lock_owner_token" | "$TRUSTED_SHA256SUM"
)"
deploy_lock_token_digest="${deploy_lock_token_digest%% *}"
deploy_lock_auth_token_name="${DEPLOY_LOCK_AUTH_TOKEN_FILE##*/}"
if [[ ! "$deploy_lock_owner_token" =~ ^[0-9a-f]{64}$ \
  || ! "$deploy_lock_identity" =~ ^[0-9]+:[0-9]+$ \
  || ! "$deploy_lock_token_identity" =~ ^[0-9]+:[0-9]+$ \
  || ! "$deploy_lock_auth_token_identity" =~ ^[0-9]+:[0-9]+$ \
  || "${DEPLOY_LOCK_AUTH_TOKEN_FILE%/*}" != "$CANONICAL_DEPLOY_LOCK_AUTH_ROOT" \
  || "$deploy_lock_auth_token_name" != "deploy-$deploy_lock_token_digest.owner-token" ]]; then
  echo "authenticated public-edge deployment lock metadata is malformed" >&2
  exit 70
fi
deploy_lock_active=1

release_deploy_lock() {
  if ((deploy_lock_active == 0)); then
    return 0
  fi
  if ! printf '%s\n' "$deploy_lock_owner_token" \
    | "$TRUSTED_ENV" -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
      "$TRUSTED_PYTHON" -I -c '
import hmac, os, re, stat, sys
lock_path = os.fsencode(sys.argv[1])
expected_lock_identity = sys.argv[2]
expected_token_identity = sys.argv[3]
expected_token = sys.stdin.buffer.read(65).decode("ascii", errors="strict").strip()
if re.fullmatch(r"[0-9a-f]{64}", expected_token) is None:
    raise SystemExit(1)
lock_stat = os.lstat(lock_path)
if (
    not stat.S_ISDIR(lock_stat.st_mode)
    or stat.S_ISLNK(lock_stat.st_mode)
    or lock_stat.st_uid != os.getuid()
    or stat.S_IMODE(lock_stat.st_mode) != 0o700
    or f"{lock_stat.st_dev}:{lock_stat.st_ino}" != expected_lock_identity
):
    raise SystemExit(1)
token_path = os.path.join(lock_path, b"owner-token")
flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(token_path, flags)
try:
    token_stat = os.fstat(descriptor)
    path_stat = os.lstat(token_path)
    actual_token = os.read(descriptor, 65).decode("ascii", errors="strict").strip()
finally:
    os.close(descriptor)
if (
    not stat.S_ISREG(token_stat.st_mode)
    or token_stat.st_nlink != 1
    or token_stat.st_uid != os.getuid()
    or stat.S_IMODE(token_stat.st_mode) != 0o600
    or (token_stat.st_dev, token_stat.st_ino) != (path_stat.st_dev, path_stat.st_ino)
    or f"{token_stat.st_dev}:{token_stat.st_ino}" != expected_token_identity
    or not hmac.compare_digest(actual_token, expected_token)
):
    raise SystemExit(1)
os.unlink(token_path)
os.rmdir(lock_path)
' "$DEPLOY_LOCK_DIR" "$deploy_lock_identity" "$deploy_lock_token_identity"; then
    return 1
  fi
  if ! printf '%s\n' "$deploy_lock_owner_token" \
    | "$TRUSTED_ENV" -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
      "$TRUSTED_PYTHON" -I -c '
import hmac, os, re, stat, sys
authorization_path = os.fsencode(sys.argv[1])
authorization_root = os.path.dirname(authorization_path)
expected_identity = sys.argv[2]
expected_token = sys.stdin.buffer.read(65).decode("ascii", errors="strict").strip()
if re.fullmatch(r"[0-9a-f]{64}", expected_token) is None:
    raise SystemExit(1)
root_stat = os.lstat(authorization_root)
if (
    not stat.S_ISDIR(root_stat.st_mode)
    or stat.S_ISLNK(root_stat.st_mode)
    or root_stat.st_uid != os.getuid()
    or stat.S_IMODE(root_stat.st_mode) != 0o700
):
    raise SystemExit(1)
flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(authorization_path, flags)
try:
    token_stat = os.fstat(descriptor)
    path_stat = os.lstat(authorization_path)
    actual_token = os.read(descriptor, 65).decode("ascii", errors="strict").strip()
finally:
    os.close(descriptor)
if (
    not stat.S_ISREG(token_stat.st_mode)
    or token_stat.st_nlink != 1
    or token_stat.st_uid != os.getuid()
    or stat.S_IMODE(token_stat.st_mode) != 0o600
    or (token_stat.st_dev, token_stat.st_ino) != (path_stat.st_dev, path_stat.st_ino)
    or f"{token_stat.st_dev}:{token_stat.st_ino}" != expected_identity
    or not hmac.compare_digest(actual_token, expected_token)
):
    raise SystemExit(1)
os.unlink(authorization_path)
root_descriptor = os.open(
    authorization_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
)
try:
    os.fsync(root_descriptor)
finally:
    os.close(root_descriptor)
' "$DEPLOY_LOCK_AUTH_TOKEN_FILE" "$deploy_lock_auth_token_identity"; then
    return 1
  fi
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
OVERLAY_PRIOR_STATE_OUTPUT="$CANONICAL_DEPLOY_RECEIPT_ROOT/active-overlay-transaction.json"
if [[ -e "$OVERLAY_PRIOR_STATE_OUTPUT" || -L "$OVERLAY_PRIOR_STATE_OUTPUT" ]]; then
  RECOVERY_ROUTE_REQUESTED=1
fi
DEPLOY_RECEIPT_DIR="$(
  "$TRUSTED_MKTEMP" -d -- "$CANONICAL_DEPLOY_RECEIPT_ROOT/deploy.XXXXXXXX"
)"
"$TRUSTED_CHMOD" 0700 -- "$DEPLOY_RECEIPT_DIR"
OVERLAY_STAGE_OUTPUT="$DEPLOY_RECEIPT_DIR/overlay-stage.json"
OVERLAY_ACTIVATION_OUTPUT="$DEPLOY_RECEIPT_DIR/overlay-activation.json"
OVERLAY_ROLLBACK_OUTPUT="$DEPLOY_RECEIPT_DIR/overlay-rollback.json"
OVERLAY_ACTIVE_PREFLIGHT_OUTPUT="$DEPLOY_RECEIPT_DIR/active-overlay-preflight.json"
OVERLAY_POSTRECREATE_PREFLIGHT_OUTPUT="$DEPLOY_RECEIPT_DIR/postrecreate-overlay-preflight.json"
DEPLOY_RECOVERY_OUTPUT="$DEPLOY_RECEIPT_DIR/deploy-recovery.json"
CANDIDATE_PROOF_BIND_SOURCE_SNAPSHOT="$DEPLOY_RECEIPT_DIR/candidate-proof-bind-source.json"
PRIOR_PROOF_AUTHORITY_SNAPSHOT="$DEPLOY_RECEIPT_DIR/prior-proof-authority-mount.json"
PRIOR_PROOF_PUBLIC_SNAPSHOT="$DEPLOY_RECEIPT_DIR/prior-proof-public-mount.json"
CANDIDATE_PORTAL_CONTAINER_NAME="chummer-public-edge-candidate-${DEPLOY_RECEIPT_DIR##*.}"
if [[ ! "$CANDIDATE_PORTAL_CONTAINER_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{7,127}$ ]]; then
  echo "generated public-edge candidate container name is invalid" >&2
  exit 70
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
  CHUMMER_PUBLIC_EDGE_PORT="$PUBLIC_EDGE_PORT"
  "$TRUSTED_DOCKER" --context "$CANONICAL_DOCKER_CONTEXT" compose
  --env-file "$ENV_FILE" -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE"
)

compose_cli() {
  "${compose_command[@]}" "$@"
}

trusted_source_python() {
  "$TRUSTED_ENV" -i \
    PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
    CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT="$BUILD_CONTEXT" \
    CHUMMER_RUN_SERVICES_CONTEXT_DIR="$SOURCE_ROOT" \
    CHUMMER_RUN_SERVICES_SOURCE="$SOURCE_ROOT" \
    CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR="$OVERLAY_ROOT" \
    CHUMMER_PUBLIC_EDGE_PORT="$PUBLIC_EDGE_PORT" \
    "$TRUSTED_PYTHON" -I "$@"
}

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

resolve_active_runtime_authority() {
  if [[ ! -e "$CANONICAL_ACTIVE_RUNTIME_AUTHORITY" \
    && ! -L "$CANONICAL_ACTIVE_RUNTIME_AUTHORITY" ]]; then
    printf 'unmanaged|0||||0||'
    return 0
  fi
  trusted_source_python -c '
import json, os, re, stat, sys
from datetime import datetime
from pathlib import Path

def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result

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
if (
    set(payload) != {"contractName", "status", "generatedAtUtc", "portal"}
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
    --compose-file "$COMPOSE_FILE" \
    --env-file "$ENV_FILE" \
    --project-name "$COMPOSE_PROJECT" \
    --build-context "$BUILD_CONTEXT" \
    --published-port "$PUBLIC_EDGE_PORT" \
    --portal-image-tag "$IMAGE_TAG" \
    --tool-image-tag "$TOOL_IMAGE_TAG" \
    --expected-runtime-proof-bind-source-sha256 \
      "$RUNTIME_PROOF_BIND_SOURCE_SHA256"
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
  if [[ "$DEPLOY_OPERATION" == deploy ]]; then
    echo "public_edge_deploy_recovered_interrupted_transaction; rerun deploy explicitly"
  else
    echo "public_edge_deploy_recovery_complete"
  fi
  exit 0
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

trusted_source_python "$ROOT_DIR/scripts/verify_public_edge_deploy_source.py" \
  "${source_gate_args[@]}"
# Combined-branch test requirement: proof hardening must provide both receipt flags
# and runtimeProofBindSource.sha256 before this deployment command is executable.
trusted_source_python "$SOURCE_ROOT/scripts/check_public_edge_deploy_preflight.py" \
  --source-root "$SOURCE_ROOT" \
  --skip-overlay-marker-check \
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256" \
  --runtime-proof-bind-source-sha256 "$RUNTIME_PROOF_BIND_SOURCE_SHA256"
compose_cli --profile install-linking-postgres-admin config --format json \
  | trusted_source_python "$SOURCE_ROOT/scripts/validate_public_edge_compose_runtime.py" \
      --project-name "$COMPOSE_PROJECT" \
      --source-root "$SOURCE_ROOT" \
      --build-context "$BUILD_CONTEXT" \
      --overlay-root "$OVERLAY_ROOT" \
      --published-port "$PUBLIC_EDGE_PORT" \
      --output "$COMPOSE_ATTESTATION_OUTPUT"

# Materialize and locally verify the replacement bind-mounted payload before either
# the image tag or live runtime is touched. The independent release-receipt digest
# binds both this staging pass and the later reuse-only activation pass.
trusted_source_python "$SOURCE_ROOT/scripts/publish_public_edge_portal_overlay.py" \
  --source-root "$SOURCE_ROOT" \
  --active-root "$OVERLAY_ROOT" \
  --staging-root "$OVERLAY_STAGING_ROOT" \
  --backup-root "$OVERLAY_BACKUP_ROOT" \
  --build-root "$OVERLAY_BUILD_ROOT" \
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256" \
  --output "$OVERLAY_STAGE_OUTPUT"

if [[ ! -f "$CANONICAL_RUNTIME_PROOF_BIND_SOURCE" \
  || -L "$CANONICAL_RUNTIME_PROOF_BIND_SOURCE" \
  || ! -O "$CANONICAL_RUNTIME_PROOF_BIND_SOURCE" ]]; then
  echo "canonical runtime proof bind source is unsafe" >&2
  exit 2
fi
runtime_proof_bind_source_sha256="$(
  "$TRUSTED_SHA256SUM" -- "$CANONICAL_RUNTIME_PROOF_BIND_SOURCE"
)"
runtime_proof_bind_source_sha256="${runtime_proof_bind_source_sha256%% *}"
if [[ "$runtime_proof_bind_source_sha256" != "$RUNTIME_PROOF_BIND_SOURCE_SHA256" ]]; then
  echo "canonical runtime proof bind source changed after preflight" >&2
  exit 2
fi
"$TRUSTED_INSTALL" -m 0600 -- \
  "$CANONICAL_RUNTIME_PROOF_BIND_SOURCE" \
  "$CANDIDATE_PROOF_BIND_SOURCE_SNAPSHOT"

resolve_image_tag_id() {
  local resolved_ids
  if ! resolved_ids="$(docker_cli image ls --quiet --no-trunc --filter "reference=$1")"; then
    return 1
  fi
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

abort_portal_recreate() {
  local failure_label="$1"
  local failure_status="$2"
  printf 'public-edge portal %s failed; invoking durable reconciliation\n' "$failure_label" >&2
  exit "$failure_status"
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
      docker_cli container cp \
        "$prior_portal_container_id:/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json" \
        "$PRIOR_PROOF_AUTHORITY_SNAPSHOT" || exit 3
      docker_cli container cp \
        "$prior_portal_container_id:/app/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json" \
        "$PRIOR_PROOF_PUBLIC_SNAPSHOT" || exit 3
      "$TRUSTED_CHMOD" 0600 -- \
        "$PRIOR_PROOF_AUTHORITY_SNAPSHOT" "$PRIOR_PROOF_PUBLIC_SNAPSHOT"
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

if ! prior_tunnel_container_id="$(compose_cli ps --all -q chummer-run-cloudflared)"; then
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
  --staging-root "$OVERLAY_STAGING_ROOT" \
  --backup-root "$OVERLAY_BACKUP_ROOT" \
  --activation-receipt "$OVERLAY_ACTIVATION_OUTPUT" \
  --proof-bind-source "$CANONICAL_RUNTIME_PROOF_BIND_SOURCE" \
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
reconcile_transaction_on_exit() {
  local failure_status="$?"
  local recovery_failed=0
  trap - EXIT HUP INT TERM
  if ((deployment_transaction_active == 1)); then
    run_deploy_recovery || recovery_failed=1
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
  abort_portal_recreate "image build journal" 1
fi

docker_cli buildx build \
  --builder "$CANONICAL_BUILDX_BUILDER" \
  --load \
  --progress="$PROGRESS" \
  -t "$IMAGE_TAG" \
  -f "$SOURCE_ROOT/Chummer.Run.Api/Dockerfile" \
  --build-context "run-services-source=$SOURCE_ROOT" \
  --build-context "fleet-media-factory-contracts=$FLEET_MEDIA_CONTRACTS" \
  --build-context "design-product=$DESIGN_PRODUCT_ROOT" \
  --build-arg "CHUMMER_BUILD_CONCURRENCY=$BUILD_CONCURRENCY" \
  "$BUILD_CONTEXT"

image_id="$(docker_cli image inspect "$IMAGE_TAG" --format '{{.Id}}')"
if [[ ! "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "could not resolve built portal image id for $IMAGE_TAG" >&2
  exit 3
fi
if ! mark_deploy_phase image_built; then
  abort_portal_recreate "image build completion journal" 1
fi

# Rebind the source-only gate after the image build. A source mutation between
# verified staging and this point fails while the exact prior runtime is live.
trusted_source_python "$SOURCE_ROOT/scripts/check_public_edge_deploy_preflight.py" \
  --source-root "$SOURCE_ROOT" \
  --skip-overlay-marker-check \
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256" \
  --runtime-proof-bind-source-sha256 "$RUNTIME_PROOF_BIND_SOURCE_SHA256"

if ! compose_cli stop chummer-run-cloudflared; then
  abort_portal_recreate "tunnel drain" 1
fi
if ! mark_deploy_phase tunnel_drained; then
  abort_portal_recreate "tunnel drain journal" 1
fi
if ((prior_portal_existed == 1 && prior_portal_was_running == 1)) \
  && ! docker_cli container stop "$prior_portal_container_id" >/dev/null; then
  abort_portal_recreate "prior portal quiesce" 1
fi
if ! mark_deploy_phase portal_stopped; then
  abort_portal_recreate "portal stop journal" 1
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
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256" \
  --runtime-proof-bind-source-sha256 "$RUNTIME_PROOF_BIND_SOURCE_SHA256" \
  --output "$OVERLAY_ACTIVE_PREFLIGHT_OUTPUT"; then
  abort_portal_recreate "active overlay preflight" 1
fi

if ! candidate_portal_create_output="$(
  compose_cli run -T -d --no-deps --service-ports --use-aliases \
    --name "$CANDIDATE_PORTAL_CONTAINER_NAME" chummer-portal
)"; then
  abort_portal_recreate "blue-green candidate creation" 1
fi
candidate_portal_container_id="$(
  docker_cli container inspect --format '{{.Id}}' \
    "$CANDIDATE_PORTAL_CONTAINER_NAME"
)" || abort_portal_recreate "candidate identity" 1
if [[ ! "$candidate_portal_container_id" =~ ^[0-9a-f]{64}$ \
  || -z "$candidate_portal_create_output" ]]; then
  abort_portal_recreate "candidate creation receipt" 1
fi
if ! mark_deploy_phase portal_candidate_started; then
  abort_portal_recreate "candidate start journal" 1
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

if ! wait_for_candidate_portal_runtime; then
  abort_portal_recreate "candidate readiness" 1
fi

# `/api/ready` is the container healthcheck and covers data-protection custody,
# PostgreSQL install-linking authority, and canonical shelf serving. Publication
# readiness additionally proves layout-v1 activation and the release-storage free-space
# admission gate before a replacement portal can be accepted.
if ! "$TRUSTED_TIMEOUT" --kill-after=5s 30s \
  "${docker_command[@]}" container exec "$candidate_portal_container_id" \
    /usr/bin/curl --fail --silent --show-error --max-time 20 \
      --output /dev/null --header 'Host: chummer.run' \
      http://127.0.0.1:8080/api/ready/publication; then
  abort_portal_recreate "publication readiness" 1
fi

# Re-read the full preflight after portal recreation, then require the runtime
# proof artifact digest to equal the value captured immediately before recreate.
# This closes a path-replacement race at the read-only proof bind boundary.
if ! trusted_source_python "$SOURCE_ROOT/scripts/check_public_edge_deploy_preflight.py" \
  --source-root "$SOURCE_ROOT" \
  --overlay-root "$OVERLAY_ROOT" \
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

verify_candidate_tunnel_runtime() {
  local candidate_tunnel_container_id candidate_tunnel_running_state
  candidate_tunnel_container_id="$(compose_cli ps --all -q chummer-run-cloudflared)" || return 1
  [[ -n "$candidate_tunnel_container_id" && "$candidate_tunnel_container_id" != *$'\n'* ]] || return 1
  if ((prior_tunnel_existed == 1)); then
    [[ "$candidate_tunnel_container_id" == "$prior_tunnel_container_id" ]] || return 1
  fi
  candidate_tunnel_running_state="$(
    docker_cli container inspect --format '{{.State.Running}}' "$candidate_tunnel_container_id"
  )" || return 1
  [[ "$candidate_tunnel_running_state" == "true" ]]
}

if ! verify_candidate_runtime_identity; then
  abort_portal_recreate "candidate image identity" 1
fi

if ((prior_tunnel_existed == 1)); then
  if ! docker_cli start "$prior_tunnel_container_id" >/dev/null \
    || [[ "$(docker_cli container inspect --format '{{.State.Running}}' "$prior_tunnel_container_id")" != "true" ]]; then
    abort_portal_recreate "tunnel restart" 1
  fi
else
  if ! compose_cli up -d --no-build --no-deps chummer-run-cloudflared; then
    abort_portal_recreate "tunnel creation" 1
  fi
fi
if ! verify_candidate_tunnel_runtime; then
  abort_portal_recreate "candidate tunnel identity" 1
fi
if ! mark_deploy_phase tunnel_started; then
  abort_portal_recreate "tunnel restart journal" 1
fi

postdeploy_command=(
  trusted_source_python "$SOURCE_ROOT/scripts/verify_public_edge_postdeploy_gate.py"
  --base-url "$BASE_URL"
  --strict-preflight
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT"
  --overlay-root "$OVERLAY_ROOT"
  --expected-build-info "$OVERLAY_ROOT/.codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
  --require-downloads-status-playwright
  --require-mobile-pwa-viewport-playwright
  --require-frontdoor-navigation-playwright
  --playwright-artifact-dir "$PLAYWRIGHT_ARTIFACT_DIR/downloads-status"
  --mobile-pwa-viewport-artifact-dir "$PLAYWRIGHT_ARTIFACT_DIR/mobile-pwa-viewport"
  --frontdoor-navigation-artifact-dir "$PLAYWRIGHT_ARTIFACT_DIR/frontdoor-navigation"
  --output "$POSTDEPLOY_OUTPUT"
)

for ((attempt = 1; attempt <= POSTDEPLOY_ATTEMPTS; attempt++)); do
  if "${postdeploy_command[@]}"; then
    break
  fi
  if ((attempt == POSTDEPLOY_ATTEMPTS)); then
    exit 1
  fi
  "$TRUSTED_SLEEP" "$POSTDEPLOY_RETRY_DELAY_SECONDS"
done

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

if ! trusted_source_python "$SOURCE_ROOT/scripts/public_edge_overlay_transaction.py" complete \
  --source-root "$SOURCE_ROOT" \
  --active-root "$OVERLAY_ROOT" \
  --output "$OVERLAY_PRIOR_STATE_OUTPUT" \
  --runtime-authority-output "$CANONICAL_ACTIVE_RUNTIME_AUTHORITY" \
  --candidate-portal-container-id "$candidate_portal_container_id" \
  --candidate-portal-container-name "$CANDIDATE_PORTAL_CONTAINER_NAME" \
  --candidate-portal-image-id "$image_id" \
  --shared-mutation-lock-token "$deploy_lock_owner_token"; then
  echo "failed to retire the completed public-edge deployment journal" >&2
  exit 70
fi
deployment_transaction_active=0
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
if ! release_deploy_lock; then
  echo "failed to release public edge deployment lock" >&2
  exit 70
fi
trap - EXIT HUP INT TERM

printf 'public_edge_portal_deployed %s\n' "$image_id"
