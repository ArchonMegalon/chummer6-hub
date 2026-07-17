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
if [[ ! "$RUNTIME_PROOF_BIND_SOURCE_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256 must be independently supplied as a lowercase SHA-256" >&2
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

OVERLAY_BASE="${OVERLAY_ROOT%/app}"
if [[ "$OVERLAY_BASE/app" != "$OVERLAY_ROOT" ]]; then
  echo "public edge overlay root must end in /app" >&2
  exit 2
fi
OVERLAY_STAGING_ROOT="${OVERLAY_BASE}-next/app"
OVERLAY_BACKUP_ROOT="${OVERLAY_BASE}-backups"
OVERLAY_BUILD_ROOT="${OVERLAY_BASE}-build"

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
  echo "an incomplete public-edge deployment journal requires reconciliation before another deploy" >&2
  exit 70
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

docker_cli() {
  "$TRUSTED_ENV" -i \
    PATH=/usr/bin:/bin \
    HOME="$CANONICAL_DOCKER_CONFIG_ROOT/home" \
    DOCKER_CONFIG="$CANONICAL_DOCKER_CONFIG_ROOT/config" \
    LANG=C LC_ALL=C \
    "$TRUSTED_DOCKER" --context "$CANONICAL_DOCKER_CONTEXT" "$@"
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

docker_context_identity="$(docker_cli context inspect "$CANONICAL_DOCKER_CONTEXT" \
  --format '{{.Name}}|{{.Endpoints.docker.Host}}|{{.Endpoints.docker.SkipTLSVerify}}')"
if [[ "$docker_context_identity" != "$CANONICAL_DOCKER_CONTEXT|$CANONICAL_DOCKER_HOST|false" ]]; then
  echo "public edge deploy refuses a non-canonical Docker daemon context" >&2
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

trusted_source_python "$ROOT_DIR/scripts/verify_public_edge_deploy_source.py" \
  "${source_gate_args[@]}"
trusted_source_python "$SOURCE_ROOT/scripts/check_public_edge_deploy_preflight.py" \
  --source-root "$SOURCE_ROOT" \
  --runtime-proof-bind-source-sha256 "$RUNTIME_PROOF_BIND_SOURCE_SHA256" \
  --skip-overlay-marker-check \
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256"
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

restore_prior_image_tag() {
  local current_image_tag_id
  current_image_tag_id="$(resolve_image_tag_id "$IMAGE_TAG")" || return 1
  if [[ -n "$prior_image_tag_id" ]]; then
    if [[ "$current_image_tag_id" != "$prior_image_tag_id" ]]; then
      docker_cli tag "$prior_image_tag_id" "$IMAGE_TAG" || return 1
    fi
  elif [[ -n "$current_image_tag_id" ]]; then
    docker_cli image rm "$IMAGE_TAG" >/dev/null || return 1
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
if [[ -z "$image_id" || "$image_id" != sha256:* ]]; then
  echo "could not resolve built portal image id for $IMAGE_TAG" >&2
  exit 3
fi

# Rebind the source-only gate after both build lanes. A source mutation between
# verified staging and this point must fail while the old runtime is still live.
trusted_source_python "$SOURCE_ROOT/scripts/check_public_edge_deploy_preflight.py" \
  --source-root "$SOURCE_ROOT" \
  --skip-overlay-marker-check \
  --release-channel-receipt "$RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$RELEASE_CHANNEL_RECEIPT_SHA256"

if ! prior_portal_container_id="$(compose_cli ps --all -q chummer-portal)"; then
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
  if ! prior_portal_image_id="$(docker_cli container inspect --format '{{.Image}}' "$prior_portal_container_id")"; then
    echo "could not inspect prior public-edge portal image" >&2
    exit 3
  fi
  if ! prior_portal_running_state="$(docker_cli container inspect --format '{{.State.Running}}' "$prior_portal_container_id")"; then
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

if ! prior_tunnel_container_id="$(compose_cli ps --all -q chummer-run-cloudflared)"; then
  echo "could not query prior public-edge tunnel container" >&2
  exit 3
fi
if [[ "$prior_tunnel_container_id" == *$'\n'* ]]; then
  echo "public-edge tunnel resolved to more than one prior container" >&2
  exit 3
fi
prior_tunnel_was_running=0
prior_tunnel_existed=0
if [[ -n "$prior_tunnel_container_id" ]]; then
  prior_tunnel_existed=1
  if ! prior_tunnel_running_state="$(docker_cli container inspect --format '{{.State.Running}}' "$prior_tunnel_container_id")"; then
    echo "could not inspect prior public-edge tunnel runtime state" >&2
    exit 3
  fi
  if [[ "$prior_tunnel_running_state" == "true" ]]; then
    prior_tunnel_was_running=1
  elif [[ "$prior_tunnel_running_state" != "false" ]]; then
    echo "prior public-edge tunnel returned an invalid runtime state" >&2
    exit 3
  fi
fi

wait_for_restored_portal_runtime() {
  local container_id="$1"
  local deadline=$((SECONDS + PORTAL_READY_TIMEOUT_SECONDS))
  local running health
  while ((SECONDS < deadline)); do
    running="$(docker_cli container inspect --format '{{.State.Running}}' "$container_id")" || return 1
    if [[ "$running" == "true" ]]; then
      health="$(docker_cli container inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")" || return 1
      case "$health" in
        healthy) return 0 ;;
        none)
          "$TRUSTED_TIMEOUT" --kill-after=5s 30s \
            "$TRUSTED_CURL" --fail --silent --show-error --max-time 20 \
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
    "$TRUSTED_SLEEP" 1
  done
  return 1
}

restore_prior_portal() {
  local restored_portal_container_id restored_portal_image_id
  if ((replacement_portal_may_exist == 1)); then
    if ! compose_cli stop chummer-portal \
      || ! compose_cli rm -f -s chummer-portal; then
      printf 'failed to remove replacement public-edge portal before rollback\n' >&2
      return 1
    fi
    replacement_portal_may_exist=0
  fi

  if ((prior_portal_existed == 0)); then
    return 0
  fi

  if ((prior_portal_was_running == 0)); then
    if docker_cli container inspect "$prior_portal_container_id" >/dev/null 2>&1; then
      prior_portal_running_state="$(docker_cli container inspect --format '{{.State.Running}}' "$prior_portal_container_id")" || return 1
      [[ "$prior_portal_running_state" == "false" ]] || return 1
      return 0
    fi
    if [[ "$prior_portal_image_id" != sha256:* ]] \
      || ! docker_cli image inspect "$prior_portal_image_id" >/dev/null 2>&1 \
      || ! docker_cli tag "$prior_portal_image_id" "$IMAGE_TAG" \
      || ! compose_cli create --no-build --force-recreate chummer-portal; then
      return 1
    fi
    prior_portal_container_id="$(compose_cli ps --all -q chummer-portal)" || return 1
    [[ -n "$prior_portal_container_id" && "$prior_portal_container_id" != *$'\n'* ]] || return 1
    [[ "$(docker_cli container inspect --format '{{.Image}}' "$prior_portal_container_id")" == "$prior_portal_image_id" ]] || return 1
    [[ "$(docker_cli container inspect --format '{{.State.Running}}' "$prior_portal_container_id")" == "false" ]] || return 1
    printf 'prior_public_edge_portal_stopped_best_effort_recreated_but_identity_changed %s\n' \
      "$prior_portal_image_id" >&2
    return 1
  fi

  if docker_cli container inspect "$prior_portal_container_id" >/dev/null 2>&1 \
    && docker_cli start "$prior_portal_container_id" >/dev/null \
    && wait_for_restored_portal_runtime "$prior_portal_container_id"; then
    printf 'prior_public_edge_portal_restarted %s\n' "$prior_portal_container_id" >&2
    return 0
  fi

  if [[ "$prior_portal_image_id" == sha256:* ]] \
    && docker_cli image inspect "$prior_portal_image_id" >/dev/null 2>&1 \
    && docker_cli tag "$prior_portal_image_id" "$IMAGE_TAG" \
    && compose_cli up -d --no-build --no-deps --force-recreate \
      --wait --wait-timeout "$PORTAL_READY_TIMEOUT_SECONDS" chummer-portal; then
    restored_portal_container_id="$(compose_cli ps --all -q chummer-portal)" || return 1
    restored_portal_image_id="$(
      docker_cli container inspect --format '{{.Image}}' "$restored_portal_container_id"
    )" || return 1
    [[ "$restored_portal_image_id" == "$prior_portal_image_id" ]] || return 1
    printf 'prior_public_edge_portal_best_effort_recreated_but_identity_changed %s\n' \
      "$prior_portal_image_id" >&2
    return 1
  fi

  printf 'failed to restore prior public-edge portal %s (%s)\n' \
    "$prior_portal_container_id" "$prior_portal_image_id" >&2
  return 1
}

restore_prior_overlay() {
  trusted_source_python "$SOURCE_ROOT/scripts/public_edge_overlay_transaction.py" restore \
    --source-root "$SOURCE_ROOT" \
    --active-root "$OVERLAY_ROOT" \
    --backup-root "$OVERLAY_BACKUP_ROOT" \
    --snapshot "$OVERLAY_PRIOR_STATE_OUTPUT" \
    --activation-receipt "$OVERLAY_ACTIVATION_OUTPUT" \
    --output "$OVERLAY_ROLLBACK_OUTPUT" \
    --shared-mutation-lock-token "$deploy_lock_owner_token"
}

restore_prior_tunnel() {
  local current_tunnel_container_id current_tunnel_running_state
  current_tunnel_container_id="$(compose_cli ps --all -q chummer-run-cloudflared)" || return 1
  [[ "$current_tunnel_container_id" != *$'\n'* ]] || return 1

  if ((prior_tunnel_existed == 0)); then
    if [[ -n "$current_tunnel_container_id" ]]; then
      compose_cli stop chummer-run-cloudflared || return 1
      compose_cli rm -f -s chummer-run-cloudflared || return 1
    fi
    [[ -z "$(compose_cli ps --all -q chummer-run-cloudflared)" ]]
    return
  fi

  # The candidate lane only stops/starts an existing tunnel; it never recreates it.
  # Losing that exact container identity therefore makes rollback authority uncertain.
  [[ "$current_tunnel_container_id" == "$prior_tunnel_container_id" ]] || return 1
  current_tunnel_running_state="$(
    docker_cli container inspect --format '{{.State.Running}}' "$prior_tunnel_container_id"
  )" || return 1
  if ((prior_tunnel_was_running == 1)); then
    if [[ "$current_tunnel_running_state" != "true" ]]; then
      docker_cli start "$prior_tunnel_container_id" >/dev/null || return 1
    fi
    [[ "$(docker_cli container inspect --format '{{.State.Running}}' "$prior_tunnel_container_id")" == "true" ]]
    return
  fi
  if [[ "$current_tunnel_running_state" == "true" ]]; then
    docker_cli stop "$prior_tunnel_container_id" >/dev/null || return 1
  elif [[ "$current_tunnel_running_state" != "false" ]]; then
    return 1
  fi
  [[ "$(docker_cli container inspect --format '{{.State.Running}}' "$prior_tunnel_container_id")" == "false" ]]
}

mark_deploy_phase() {
  trusted_source_python "$SOURCE_ROOT/scripts/public_edge_overlay_transaction.py" mark-phase \
    --source-root "$SOURCE_ROOT" \
    --active-root "$OVERLAY_ROOT" \
    --output "$OVERLAY_PRIOR_STATE_OUTPUT" \
    --phase "$1" \
    --shared-mutation-lock-token "$deploy_lock_owner_token"
}

portal_transaction_active=0
replacement_portal_may_exist=0
rollback_portal_on_exit() {
  local failure_status="$?"
  local rollback_failed=0
  local portal_quiesced=0
  local overlay_restored=0
  local portal_restored=0
  trap - EXIT
  if ((portal_transaction_active == 1)); then
    compose_cli stop chummer-run-cloudflared >/dev/null 2>&1 || rollback_failed=1
    if compose_cli stop chummer-portal >/dev/null 2>&1; then
      portal_quiesced=1
    else
      rollback_failed=1
    fi
    if ((portal_quiesced == 1)) && restore_prior_overlay; then
      overlay_restored=1
    else
      rollback_failed=1
    fi
  fi
  if ((image_tag_transaction_active == 1)); then
    restore_prior_image_tag || rollback_failed=1
  fi
  if ((portal_transaction_active == 1 && overlay_restored == 1)); then
    if restore_prior_portal; then
      portal_restored=1
    else
      rollback_failed=1
    fi
  fi
  if ((portal_transaction_active == 1)); then
    # Tunnel restoration is independent: a known prior tunnel must not remain
    # drained merely because another rollback component is uncertain.
    restore_prior_tunnel || rollback_failed=1
    if ((overlay_restored == 0 || portal_restored == 0)); then
      rollback_failed=1
    fi
  fi
  if ((rollback_failed == 0)); then
    "$TRUSTED_RM" -f -- "$OVERLAY_PRIOR_STATE_OUTPUT" || rollback_failed=1
  fi
  release_deploy_lock || rollback_failed=1
  if ((rollback_failed == 1)); then
    printf 'public-edge rollback did not restore the exact prior overlay, runtime, tunnel, and image tag\n' >&2
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

# This fixed, durable journal is created immediately before the first runtime
# mutation. A crash leaves it in place, so a later deploy fails closed instead of
# silently treating a mixed cutover as its new prior state.
if ! trusted_source_python "$SOURCE_ROOT/scripts/public_edge_overlay_transaction.py" snapshot \
  --source-root "$SOURCE_ROOT" \
  --active-root "$OVERLAY_ROOT" \
  --output "$OVERLAY_PRIOR_STATE_OUTPUT" \
  --shared-mutation-lock-token "$deploy_lock_owner_token" \
  --prior-image-tag-id "$prior_image_tag_id" \
  --prior-portal-container-id "$prior_portal_container_id" \
  --prior-portal-image-id "$prior_portal_image_id" \
  --prior-portal-existed "$prior_portal_existed" \
  --prior-portal-was-running "$prior_portal_was_running" \
  --prior-tunnel-container-id "$prior_tunnel_container_id" \
  --prior-tunnel-existed "$prior_tunnel_existed" \
  --prior-tunnel-was-running "$prior_tunnel_was_running"; then
  "$TRUSTED_RM" -f -- "$OVERLAY_PRIOR_STATE_OUTPUT"
  exit 1
fi
portal_transaction_active=1
if ! compose_cli stop chummer-run-cloudflared; then
  abort_portal_recreate "tunnel drain" 1
fi
if ! mark_deploy_phase tunnel_drained; then
  abort_portal_recreate "tunnel drain journal" 1
fi
if ! compose_cli stop chummer-portal; then
  abort_portal_recreate "quiesce" 1
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
  --output "$OVERLAY_ACTIVE_PREFLIGHT_OUTPUT"; then
  abort_portal_recreate "active overlay preflight" 1
fi

replacement_portal_may_exist=1
if ! compose_cli up -d --no-build --no-deps --force-recreate \
  --wait --wait-timeout "$PORTAL_READY_TIMEOUT_SECONDS" chummer-portal; then
  abort_portal_recreate "recreation" 1
fi
if ! mark_deploy_phase portal_recreated; then
  abort_portal_recreate "portal recreation journal" 1
fi

# `/api/ready` is the container healthcheck and covers data-protection custody,
# PostgreSQL install-linking authority, and canonical shelf serving. Publication
# readiness additionally proves layout-v1 activation and the release-storage free-space
# admission gate before a replacement portal can be accepted.
if ! "$TRUSTED_TIMEOUT" --kill-after=5s 30s \
  "${compose_command[@]}" exec -T chummer-portal \
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

container_proof_sha256() {
  local proof_path="$1"
  local rendered digest
  rendered="$(
    compose_cli exec -T chummer-portal /usr/bin/sha256sum -- "$proof_path"
  )" || return 1
  digest="${rendered%% *}"
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  [[ "$rendered" == "$digest  $proof_path" ]] || return 1
  printf '%s' "$digest"
}

if ! proof_authority_mount_sha256="$(
  container_proof_sha256 /proofs/HUB_LOCAL_RELEASE_PROOF.generated.json
)"; then
  abort_portal_recreate "runtime proof authority mount identity" 1
fi
if ! proof_public_mount_sha256="$(
  container_proof_sha256 \
    /app/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json
)"; then
  abort_portal_recreate "runtime proof public mount identity" 1
fi
if [[ "$proof_authority_mount_sha256" != "$runtime_proof_sha256" \
  || "$proof_public_mount_sha256" != "$runtime_proof_sha256" ]]; then
  abort_portal_recreate "runtime proof mounted-byte identity" 1
fi

verify_candidate_runtime_identity() {
  local candidate_container_id candidate_container_image_id candidate_tag_image_id
  candidate_container_id="$(compose_cli ps --all -q chummer-portal)" || return 1
  [[ -n "$candidate_container_id" && "$candidate_container_id" != *$'\n'* ]] || return 1
  candidate_container_image_id="$(docker_cli container inspect --format '{{.Image}}' "$candidate_container_id")" || return 1
  candidate_tag_image_id="$(resolve_image_tag_id "$IMAGE_TAG")" || return 1
  [[ "$candidate_container_image_id" == "$image_id" && "$candidate_tag_image_id" == "$image_id" ]]
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

portal_transaction_active=0
replacement_portal_may_exist=0
image_tag_transaction_active=0
if ! "$TRUSTED_RM" -f -- "$OVERLAY_PRIOR_STATE_OUTPUT"; then
  echo "failed to retire the completed public-edge deployment journal" >&2
  exit 70
fi
if ! release_deploy_lock; then
  echo "failed to release public edge deployment lock" >&2
  exit 70
fi
trap - EXIT HUP INT TERM

printf 'public_edge_portal_deployed %s\n' "$image_id"
