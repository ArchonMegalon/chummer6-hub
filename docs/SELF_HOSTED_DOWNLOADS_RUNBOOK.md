# Self-Hosted Downloads Runbook

Purpose: publish desktop artifacts to a self-hosted downloads surface and verify that `/downloads/releases.json` serves non-empty artifacts.

For the full active-head artifact set, including the hosted API bundle, use `ACTIVE_HEAD_RELEASE_ARTIFACTS.md`.

Registry note:
`/downloads/releases.json` is now treated as a compatibility projection.
The canonical promoted release record is `RELEASE_CHANNEL.generated.json`, materialized by `chummer6-hub-registry`.
When available, Hub may consume the registry runtime endpoint directly via `CHUMMER_RELEASE_REGISTRY_CURRENT_URL`
or `CHUMMER_HUB_REGISTRY_BASE_URL`; the file-backed manifest remains the fallback.

## Prerequisites

1. Desktop bundle exists (`desktop-download-bundle` layout):
registry-generated `RELEASE_CHANNEL.generated.json`, compatibility `releases.json`, and `files/chummer-*`.
2. Portal serves `/downloads/releases.json` as a compatibility view from your storage topology and should carry the registry-owned `RELEASE_CHANNEL.generated.json` alongside it.
3. Use preapproved runbook/script paths from repository root (`/docker/chummer5a`).
4. `RUNBOOK_LOG_DIR` is mandatory and must name a caller-owned mode-`0700`, symlink-free,
persistent child of `/docker/chummercomplete/.state/public-edge-cutover-receipts`. Never place
cutover evidence in `/tmp`. `RUNBOOK_STATE_DIR` may pin other writable tool state (for example
`DOTNET_CLI_HOME`) to a known writable directory.

## Public-edge mutable storage preflight

The portal process remains non-root and defaults to UID/GID `1654:1654`. Before Buildx can retag the canonical image, the governed deploy writes a durable journal containing the exact prior overlay, image tags, portal and tunnel identities and running states, the externally approved candidate runtime-proof SHA-256, and the prior running portal's two independently measured proof-mount digests. It also preserves owner-only snapshots of the candidate proof and, when the prior portal was running, both prior mounted proof files. The deploy starts a uniquely named blue/green candidate and does not destroy the exact prior portal until the candidate runtime authority is durably committed and the transaction journal is retired.

Recovery first removes only the journal-named candidate after verifying its Compose project, service, and one-off labels. It then restores the exact prior overlay and tags. A prior portal that was absent remains absent; one that was stopped remains stopped, and neither state is subjected to an impossible in-container proof check. To restart a previously running portal, recovery temporarily installs the separately journaled prior proof bytes at the canonical bind source, starts the exact old container so Docker captures that old inode, atomically restores the candidate proof source, and verifies both old in-container mount digests before restoring the tunnel. Missing old authority, identity drift, or either proof mismatch remains fail-closed and retains the journal. The Compose service dependency still requires successful initialization during normal startup. This one-shot service has no network, a read-only root filesystem, `no-new-privileges`, all capabilities dropped except `CHOWN`, `SETUID`, and `SETGID`, and no secret mounts. It migrates the four named mutable roots (`chummer-run-api-state`, `chummer-release-upload-sessions`, `chummer-windows-proof-store`, and `chummer-windows-proof-upload-sessions`) and then creates and removes an owner-only probe as the configured portal identity. Symlinks and special files in those roots fail the preflight.

`/downloads-source` is a host bind, not a named volume. The initializer only creates and removes a probe there; it never changes host ownership or modes. Before deployment, the operator must grant the configured portal identity create, write, and delete access. Choose one governed host-side policy and verify it locally, for example:

```bash
# Simple dedicated-owner policy.
sudo chown -R 1654:1654 /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads

# Or preserve the current owner and grant an access/default ACL.
sudo setfacl -Rm u:1654:rwX,d:u:1654:rwX /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads
```

Do not make the downloads tree world-writable. If `CHUMMER_PORTAL_UID` or `CHUMMER_PORTAL_GID` changes, rebuild the app image with the matching Docker build arguments and update the host ownership/ACL before recreating the portal.

The read-only data-protection certificate, certificate-password file, and InstallLinking PostgreSQL runtime connection file are also outside the initializer's authority. On the host, each must be explicitly readable by the configured UID/GID while remaining inaccessible to other users (normally portal-owned mode `0400`, or a narrowly scoped ACL on a root-owned mode `0600` file). Never mount these files into the initializer. The guarded deploy wrapper and image-restore tool abort before portal recreation if the volume preflight fails.

The guarded deploy wrapper runs the strict public-edge source preflight and closed Compose runtime attestation before `buildx` can retag the local image. The latter makes the required PKCS#12, password-file, PostgreSQL credential, runtime-role, and release-shelf posture inputs fail before any build or portal quiesce. After the one-shot initializer, the wrapper starts the blue/green candidate by exact name, waits for its `/api/ready` healthcheck, and then requires `/api/ready/publication`, which additionally proves layout-v1 activation and the configured release-storage free-space admission thresholds. The candidate stays transactional through the full browser-backed postdeploy gate. Any ordinary failure invokes the same idempotent recovery command used after a hard crash; an uncertain recovery exits with status `70` and preserves its journal.

## Recommended Production Topology

1. Default recommendation: use `CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR` with a self-hosted runner that can write directly into the portal downloads storage mount.
2. Reason: this keeps `/downloads/` self-hosted, lets the deploy job verify both the local manifest file and the live portal manifest, and matches the canonical topology enforced in repo docs.
3. Treat object storage as the alternate topology for environments where the runner cannot write to portal storage directly; keep portal proxying and live manifest verification enabled there too.
4. Start from [`docs/examples/self-hosted-downloads.env.example`](examples/self-hosted-downloads.env.example) and adapt it to your portal base URL and storage target.

## Install-linking PostgreSQL authority cutover and recovery

The public-edge stack uses a managed/external PostgreSQL authority; this Compose file deliberately
does not deploy a database. Configure distinct owner-only runtime and migrator connection files with
`SSL Mode=VerifyFull`, and make the provider certificate chain available through the image's system
trust store. The runtime LOGIN role named by `CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE` must
already exist. `prepare` migrates the schema and grants that existing role; it never creates a LOGIN.

Stage and verify the replacement overlay, build both current images, then perform the cutover in
this exact drain/stop/activate/probe/prepare/conditional-import/validate/start/prove/restore order. Staging does not
change the active overlay. Activation happens only after the currently bind-mounted portal is
stopped. Keep Cloudflare Tunnel and the portal stopped for the whole database-administration window
so public traffic cannot reach a partially cut-over instance and the portal's local writer lease
cannot race the one-time import. Every operator job is bounded by the outer `timeout`; the tool has
no permission to turn an unbounded wait into a successful cutover.

Save the following body in a caller-owned mode-`0600` file under the canonical state root. Do not
paste it into an existing shell. Launch it only through `/usr/bin/env -i` and a noninteractive Bash
with startup files disabled, passing only the variables named by the body. The launcher must set
`CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1`; for example:

```bash
/usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C \
  HOME=/docker/chummercomplete/.state/public-edge-runbook-home \
  CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1 \
  CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD="$CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD" \
  CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF="$CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF" \
  CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256="$CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256" \
  CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT="$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT" \
  CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256="$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256" \
  CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256="$CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256" \
  CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL="$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL" \
  CHUMMER_RUN_SERVICES_SOURCE="$CHUMMER_RUN_SERVICES_SOURCE" \
  CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT="$CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT" \
  CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR="$CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR" \
  RUNBOOK_LOG_DIR="$RUNBOOK_LOG_DIR" \
  CODEXLIZ_CF_ACCESS_CLIENT_ID="$CODEXLIZ_CF_ACCESS_CLIENT_ID" \
  CODEXLIZ_CF_ACCESS_CLIENT_SECRET="$CODEXLIZ_CF_ACCESS_CLIENT_SECRET" \
  /usr/bin/bash --noprofile --norc \
  /docker/chummercomplete/.state/public-edge-cutover-runbook/run.sh
```

This boundary excludes `BASH_ENV`, `ENV`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, and ambient Docker,
BuildKit, Buildx, and Compose routing before Bash starts. A sentinel without this clean launcher is
not an authorization substitute.

```bash
(
set -euo pipefail
umask 077

: "${CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH:?Run through the documented clean-shell launcher}"
test "$CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH" = 1 || exit 78
: "${CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD:?Export the independently selected full 40-hex commit}"
: "${CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF:?Export its exact refs/remotes/... authority}"
: "${CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256:?Export the independently selected verifier SHA-256}"
: "${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT:?Export the selected release-channel receipt path}"
: "${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256:?Export its independently selected SHA-256}"
: "${CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256:?Export the independently selected canonical runtime-proof SHA-256}"
: "${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL:?Export public_stable, stable, preview, or nightly}"
: "${CHUMMER_RUN_SERVICES_SOURCE:?Export the absolute run-services source root used by Compose}"
: "${CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT:?Export the absolute public-edge Docker build context}"
: "${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR:?Export the absolute portal /app overlay root used by Compose}"
: "${RUNBOOK_LOG_DIR:?Export a persistent cutover receipt directory under /docker/chummercomplete/.state/public-edge-cutover-receipts}"
: "${CODEXLIZ_CF_ACCESS_CLIENT_ID:?Export the governed Cloudflare Access client id}"
: "${CODEXLIZ_CF_ACCESS_CLIENT_SECRET:?Export the governed Cloudflare Access client secret}"

trusted_run_services_root=/docker/chummercomplete/chummer.run-services
trusted_source_verifier="$trusted_run_services_root/scripts/verify_public_edge_deploy_authority.py"
for trusted_tool in /usr/bin/env /usr/bin/git /usr/bin/python3 /usr/bin/docker \
  /usr/bin/curl /usr/bin/timeout /usr/bin/realpath /usr/bin/stat /usr/bin/id \
  /usr/bin/mktemp /usr/bin/chmod /usr/bin/install /usr/bin/mkdir /usr/bin/rmdir \
  /usr/bin/rm /usr/bin/date /usr/bin/awk /usr/bin/printf /usr/bin/sha256sum \
  /usr/bin/sync; do
  test -x "$trusted_tool" || {
    echo "Required trusted tool is unavailable: $trusted_tool" >&2
    exit 78
  }
done
test -f "$trusted_source_verifier" && ! test -L "$trusted_source_verifier" || {
  echo "The trusted public-edge source verifier is unavailable or symlinked." >&2
  exit 78
}

# Do not inherit interpreters, shell hooks, or Docker/Compose routing. Values are never logged.
for ambient_name in $(/usr/bin/env | /usr/bin/awk -F= '{print $1}'); do
  case "$ambient_name" in
    PYTHONPATH|PYTHONHOME|PYTHONSTARTUP|PYTHONINSPECT|PYTHONBREAKPOINT|PYTHONWARNINGS|PYTHONSAFEPATH|\
    BASH_ENV|ENV|CDPATH|LD_PRELOAD|LD_LIBRARY_PATH|DOCKER_HOST|DOCKER_CONTEXT|DOCKER_CONFIG|\
    BUILDKIT_HOST|BUILDX_*|COMPOSE_*)
      echo "Forbidden ambient execution-routing variable is set: $ambient_name" >&2
      exit 78
      ;;
  esac
done
PATH=/usr/bin:/bin
export PATH

[[ "$CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
  echo "The independently selected trusted-verifier digest must be a full lowercase SHA-256." >&2
  exit 78
}
[[ "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
  echo "The independently selected release-channel receipt digest must be a full lowercase SHA-256." >&2
  exit 78
}
[[ "$CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
  echo "The independently selected runtime-proof digest must be a full lowercase SHA-256." >&2
  exit 78
}
trusted_verifier_actual_sha256="$(/usr/bin/sha256sum -- "$trusted_source_verifier")"
trusted_verifier_actual_sha256="${trusted_verifier_actual_sha256%% *}"
test "$trusted_verifier_actual_sha256" = "$CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256" || {
  echo "The fixed trusted-verifier bytes do not match the independently selected digest." >&2
  exit 78
}

canonical_receipt_root=/docker/chummercomplete/.state/public-edge-cutover-receipts
test "$(/usr/bin/realpath -e -- "$canonical_receipt_root")" = "$canonical_receipt_root" || {
  echo "The canonical cutover receipt root is missing, ambiguous, or symlinked." >&2
  exit 78
}
case "$RUNBOOK_LOG_DIR" in
  "$canonical_receipt_root"/*) ;;
  *) echo "RUNBOOK_LOG_DIR must be a persistent child of $canonical_receipt_root." >&2; exit 78 ;;
esac
test "$(/usr/bin/realpath -e -- "$RUNBOOK_LOG_DIR")" = "$RUNBOOK_LOG_DIR" \
  && test "$(/usr/bin/stat -c %u -- "$RUNBOOK_LOG_DIR")" -eq "$(/usr/bin/id -u)" \
  && test "$(/usr/bin/stat -c %a -- "$RUNBOOK_LOG_DIR")" = 700 || {
    echo "RUNBOOK_LOG_DIR must be an existing caller-owned mode-0700 symlink-free directory." >&2
    exit 78
  }

# This wrapper-owned minimal gate is the first Python execution. It validates the selected tree,
# full commit, configured branch upstream, and independently selected remote ref before source code.
trusted_source_authority_receipt="$(/usr/bin/mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-public-edge-trusted-source.XXXXXX.json")"
/usr/bin/chmod 600 "$trusted_source_authority_receipt"
/usr/bin/timeout --kill-after=5s 60s \
  /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
  /usr/bin/python3 -I "$trusted_source_verifier" \
  --repo-root "$CHUMMER_RUN_SERVICES_SOURCE" \
  --expected-head "$CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD" \
  --expected-upstream-ref "$CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF" \
  >"$trusted_source_authority_receipt"

normalize_existing_root() {
  root_label="$1"
  root_value="$2"
  /usr/bin/timeout --kill-after=5s 15s \
    /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
    /usr/bin/python3 -I -S - "$root_label" "$root_value" <<'PY'
import os
from pathlib import Path
import stat
import sys

label, raw = sys.argv[1:]
if not raw.startswith("/") or any(ord(character) < 32 or ord(character) == 127 for character in raw):
    raise SystemExit(f"{label} must be an absolute path without control characters")

normalized = Path(os.path.normpath(raw))
if not normalized.is_absolute() or normalized == Path("/"):
    raise SystemExit(f"{label} must resolve to a non-root absolute directory")

current = Path(normalized.anchor)
for component in normalized.parts[1:]:
    current /= component
    try:
        metadata = current.lstat()
    except OSError as error:
        raise SystemExit(f"{label} cannot be inspected at {current}: {error}") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise SystemExit(f"{label} contains a symlink component: {current}")

if not normalized.is_dir():
    raise SystemExit(f"{label} is not an existing directory: {normalized}")
try:
    resolved = normalized.resolve(strict=True)
except OSError as error:
    raise SystemExit(f"{label} cannot be resolved: {error}") from error
if resolved != normalized:
    raise SystemExit(f"{label} is ambiguous after normalization: {normalized} != {resolved}")
sys.stdout.write(str(resolved))
PY
}

source_root="$(normalize_existing_root \
  CHUMMER_RUN_SERVICES_SOURCE "$CHUMMER_RUN_SERVICES_SOURCE")"
build_context="$(normalize_existing_root \
  CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT "$CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT")"
active_root="$(normalize_existing_root \
  CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR "$CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR")"
case "$active_root" in
  */app) ;;
  *) echo "The normalized portal overlay root must end in /app." >&2; exit 78 ;;
esac
export CHUMMER_RUN_SERVICES_SOURCE="$source_root"
export CHUMMER_RUN_SERVICES_CONTEXT_DIR="$source_root"
export CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT="$build_context"
export CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR="$active_root"
cd -- "$source_root"

canonical_env_file=/docker/chummercomplete/chummer.run-services/.env
canonical_docker_config_root=/docker/chummercomplete/.state/public-edge-docker-cli
test "$(/usr/bin/realpath -e -- "$canonical_env_file")" = "$canonical_env_file" \
  && test -f "$canonical_env_file" && ! test -L "$canonical_env_file" || {
    echo "The canonical Compose environment file is missing, ambiguous, or symlinked." >&2
    exit 78
  }
/usr/bin/install -d -m 0700 -- "$canonical_docker_config_root" \
  "$canonical_docker_config_root/home" "$canonical_docker_config_root/config"
for docker_state_dir in "$canonical_docker_config_root" \
  "$canonical_docker_config_root/home" "$canonical_docker_config_root/config"; do
  test "$(/usr/bin/realpath -e -- "$docker_state_dir")" = "$docker_state_dir" \
    && test "$(/usr/bin/stat -c %u -- "$docker_state_dir")" -eq "$(/usr/bin/id -u)" \
    && test "$(/usr/bin/stat -c %a -- "$docker_state_dir")" = 700 || {
      echo "Canonical Docker CLI state must be caller-owned mode 0700 and symlink-free." >&2
      exit 78
    }
done

# All Docker and Compose operations pass through one clean local-daemon authority. The only Compose
# file input is the canonical env file plus these audited nonsecret path/port bindings.
docker_command=(
  /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C
  HOME="$canonical_docker_config_root/home"
  DOCKER_CONFIG="$canonical_docker_config_root/config"
  CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT="$build_context"
  CHUMMER_RUN_SERVICES_CONTEXT_DIR="$source_root"
  CHUMMER_RUN_SERVICES_SOURCE="$source_root"
  CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR="$active_root"
  CHUMMER_PUBLIC_EDGE_PORT=8091
  /usr/bin/docker --context default
)
docker_context_identity="$("${docker_command[@]}" context inspect default \
  --format '{{.Name}}|{{.Endpoints.docker.Host}}|{{.Endpoints.docker.SkipTLSVerify}}')"
test "$docker_context_identity" = 'default|unix:///var/run/docker.sock|false' || {
  echo "The runbook refuses a non-canonical Docker daemon context." >&2
  exit 78
}
builder_identity="$(
  "${docker_command[@]}" buildx ls --format json |
    /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
    /usr/bin/python3 -I -c '
import json, sys
matches = []
for line in sys.stdin:
    if not line.strip():
        continue
    item = json.loads(line)
    if item.get("Name") != "default":
        continue
    matches.append(item)
if len(matches) != 1:
    raise SystemExit(1)
item = matches[0]
nodes = item.get("Nodes")
if (item.get("Current") is not True or item.get("Driver") != "docker"
        or not isinstance(nodes, list) or len(nodes) != 1
        or nodes[0].get("Name") != "default" or nodes[0].get("Endpoint") != "default"
        or nodes[0].get("Status") != "running"):
    raise SystemExit(1)
print("default|docker|default|running")
'
)"
test "$builder_identity" = 'default|docker|default|running' || {
  echo "The runbook refuses a non-canonical Buildx builder." >&2
  exit 78
}

# Acquire the one shared host mutation authority through the same crash-consistent helper used by
# restore. It fsyncs a unique external recovery capability and a complete staging lock, then uses
# renameat2(RENAME_NOREPLACE) so the fixed lock is never visible without its owner token.
mutation_lock_helper="$source_root/scripts/public_edge_mutation_lock.py"
cutover_lease_receipt="$(/usr/bin/mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-public-edge-mutation-lease.XXXXXX.json")"
/usr/bin/chmod 600 "$cutover_lease_receipt"
/usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
  /usr/bin/python3 -I "$mutation_lock_helper" acquire \
  --actor cutover --output "$cutover_lease_receipt" >/dev/null
cutover_recovery_authorization_file="$(/usr/bin/env -i \
  PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
  /usr/bin/python3 -I -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["authorizationPath"])' \
  "$cutover_lease_receipt")"
cutover_lock_token="$(/usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
  /usr/bin/python3 -I -c '
import os,re,stat,sys
p=sys.argv[1]; s=os.lstat(p)
if stat.S_ISLNK(s.st_mode) or not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or stat.S_IMODE(s.st_mode) != 0o600:
    raise SystemExit(1)
v=open(p, encoding="ascii").read().strip()
if re.fullmatch(r"[0-9a-f]{64}", v) is None: raise SystemExit(1)
print(v)
' "$cutover_recovery_authorization_file")"
cutover_lock_dir=/docker/chummercomplete/.state/public-edge-mutation.lock
cutover_lease_active=1
cutover_drained=0
operator_jobs_started=0
image_tag_rollback_active=0
image_tags_committed=0
prior_portal_image_tag_id=""
prior_postgres_tool_image_tag_id=""
cf_access_header_file=""

release_cutover_lease() {
  if test "$cutover_lease_active" -eq 0; then return 0; fi
  /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
    /usr/bin/python3 -I "$mutation_lock_helper" release \
    --lease-receipt "$cutover_lease_receipt" >/dev/null || return
  cutover_lease_active=0
}

release_initial_cutover_lock() {
  initial_status=$?
  trap - EXIT HUP INT TERM
  release_cutover_lease || exit 70
  exit "$initial_status"
}
trap release_initial_cutover_lock EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Resolve Compose while holding the mutation lock. Stream the secret-bearing render directly into
# the selected-and-source-gated full runtime attestor; persist only its nonsecret closed-policy
# receipt. The weak root-binding-only projection is intentionally not an acceptance authority.
compose_runtime_attestation_receipt="$(/usr/bin/mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-compose-runtime.XXXXXX.json")"
/usr/bin/chmod 600 "$compose_runtime_attestation_receipt"
/usr/bin/timeout --kill-after=5s 60s \
  "${docker_command[@]}" compose --env-file "$canonical_env_file" -p chummer6-hub \
  -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
  config --format json |
  /usr/bin/timeout --kill-after=5s 30s \
  /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
  /usr/bin/python3 -I "$source_root/scripts/validate_public_edge_compose_runtime.py" \
  --project-name chummer6-hub --source-root "$source_root" \
  --build-context "$build_context" --overlay-root "$active_root" \
  --published-port 8091 --output "$compose_runtime_attestation_receipt"

overlay_base="${active_root%/app}"
active_build_info="$active_root/.codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
cutover_started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cutover_id="$(date -u +%Y%m%dT%H%M%SZ)"

operator_job_ids() {
  admin_job_ids="$(/usr/bin/timeout --kill-after=5s 15s "${docker_command[@]}" ps -aq \
    --filter label=com.docker.compose.project=chummer6-hub \
    --filter label=com.docker.compose.service=chummer-install-linking-postgres-admin)" || return
  import_job_ids="$(/usr/bin/timeout --kill-after=5s 15s "${docker_command[@]}" ps -aq \
    --filter label=com.docker.compose.project=chummer6-hub \
    --filter label=com.docker.compose.service=chummer-install-linking-postgres-import)" || return
  if test -n "$admin_job_ids"; then printf '%s\n' "$admin_job_ids"; fi
  if test -n "$import_job_ids"; then printf '%s\n' "$import_job_ids"; fi
}

stop_operator_jobs() {
  operator_job_ids 2>/dev/null | while IFS= read -r container_id; do
    if test -n "$container_id"; then
      /usr/bin/timeout --kill-after=5s 20s "${docker_command[@]}" rm --force "$container_id" \
        >/dev/null 2>&1 || true
    fi
  done
}

assert_no_operator_jobs() {
  operator_jobs="$(operator_job_ids)"
  if test -n "$operator_jobs"; then
    echo "An install-linking PostgreSQL operator container is still present." >&2
    return 1
  fi
}

run_operator_job_and_verify_image() {
  operator_service="$1"
  operator_name="$2"
  operator_log="$3"
  shift 3
  /usr/bin/timeout --kill-after=10s 180s \
    "${docker_command[@]}" compose --env-file "$canonical_env_file" -p chummer6-hub \
    -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
    run --name "$operator_name" "$operator_service" "$@" \
    >"$operator_log" 2>&1 || return
  operator_container_id="$(/usr/bin/timeout --kill-after=5s 30s \
    "${docker_command[@]}" container inspect --format '{{.Id}}' "$operator_name")" || return
  case "$operator_container_id" in ""|*$'\n'*) return 1 ;; esac
  operator_container_image_id="$(/usr/bin/timeout --kill-after=5s 30s \
    "${docker_command[@]}" container inspect --format '{{.Image}}' "$operator_container_id")" || return
  test "$operator_container_image_id" = "$candidate_postgres_tool_image_id" || return
  test "$(/usr/bin/timeout --kill-after=5s 30s "${docker_command[@]}" container inspect \
    --format '{{ index .Config.Labels "com.docker.compose.project" }}' \
    "$operator_container_id")" = chummer6-hub || return
  test "$(/usr/bin/timeout --kill-after=5s 30s "${docker_command[@]}" container inspect \
    --format '{{ index .Config.Labels "com.docker.compose.service" }}' \
    "$operator_container_id")" = "$operator_service" || return
  /usr/bin/timeout --kill-after=5s 30s "${docker_command[@]}" rm "$operator_container_id" >/dev/null || return
  printf '%s' "$operator_container_image_id"
}

probe_local_install_linking_store_presence() {
  operator_service="$1"
  operator_name="$2"
  operator_log="$3"
  if /usr/bin/timeout --kill-after=10s 180s \
    "${docker_command[@]}" compose --env-file "$canonical_env_file" -p chummer6-hub \
    -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
    run --name "$operator_name" --entrypoint /bin/sh "$operator_service" -c \
    'store=/app/state/install-linking/install-linking-store.json; if test -e "$store" || test -L "$store" || test -e "$store.floor" || test -L "$store.floor"; then exit 0; else exit 42; fi' \
    >"$operator_log" 2>&1; then
    operator_run_status=0
  else
    operator_run_status=$?
  fi
  operator_container_id="$(/usr/bin/timeout --kill-after=5s 30s \
    "${docker_command[@]}" container inspect --format '{{.Id}}' "$operator_name")" || return
  case "$operator_container_id" in ""|*$'\n'*) return 1 ;; esac
  operator_container_image_id="$(/usr/bin/timeout --kill-after=5s 30s \
    "${docker_command[@]}" container inspect --format '{{.Image}}' "$operator_container_id")" || return
  operator_container_exit_code="$(/usr/bin/timeout --kill-after=5s 30s \
    "${docker_command[@]}" container inspect --format '{{.State.ExitCode}}' \
    "$operator_container_id")" || return
  test "$operator_container_image_id" = "$candidate_postgres_tool_image_id" || return
  test "$operator_container_exit_code" = "$operator_run_status" || return
  test "$(/usr/bin/timeout --kill-after=5s 30s "${docker_command[@]}" container inspect \
    --format '{{ index .Config.Labels "com.docker.compose.project" }}' \
    "$operator_container_id")" = chummer6-hub || return
  test "$(/usr/bin/timeout --kill-after=5s 30s "${docker_command[@]}" container inspect \
    --format '{{ index .Config.Labels "com.docker.compose.service" }}' \
    "$operator_container_id")" = "$operator_service" || return
  /usr/bin/timeout --kill-after=5s 30s \
    "${docker_command[@]}" rm "$operator_container_id" >/dev/null || return
  case "$operator_run_status" in
    0) printf present ;;
    42) printf absent ;;
    *) return 1 ;;
  esac
}

resolve_mutable_image_tag_id() {
  image_tag="$1"
  resolved_ids="$(/usr/bin/timeout --kill-after=5s 30s "${docker_command[@]}" image ls --quiet --no-trunc \
    --filter reference="$image_tag")" || return
  resolved_ids="$(printf '%s\n' "$resolved_ids" | awk 'NF && !seen[$0]++')"
  case "$resolved_ids" in *$'\n'*) return 1 ;; esac
  printf '%s' "$resolved_ids"
}

require_full_image_id() {
  image_id="$1"
  [[ "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || {
    echo "A mutable image tag did not resolve to a full lowercase SHA-256 image id." >&2
    return 1
  }
}

restore_prior_mutable_image_tag() {
  image_tag="$1"
  prior_image_tag_id="$2"
  current_image_tag_id="$(resolve_mutable_image_tag_id "$image_tag")" || return
  if test -n "$prior_image_tag_id"; then
    if test "$current_image_tag_id" != "$prior_image_tag_id"; then
      /usr/bin/timeout --kill-after=5s 30s "${docker_command[@]}" tag \
        "$prior_image_tag_id" "$image_tag" || return
    fi
  elif test -n "$current_image_tag_id"; then
    /usr/bin/timeout --kill-after=5s 30s "${docker_command[@]}" image rm "$image_tag" >/dev/null || return
  fi
}

cutover_cleanup() {
  cleanup_status=$?
  cleanup_failed=0
  trap - EXIT HUP INT TERM
  if test "$operator_jobs_started" -eq 1; then
    stop_operator_jobs || cleanup_failed=1
  fi
  if test "$cutover_drained" -eq 1; then
    /usr/bin/timeout --kill-after=10s 60s \
      "${docker_command[@]}" compose --env-file "$canonical_env_file" -p chummer6-hub \
      -f docker-compose.public-edge.yml \
      stop chummer-run-cloudflared chummer-portal >/dev/null 2>&1 || cleanup_failed=1
  fi
  if test "$image_tag_rollback_active" -eq 1 \
    && test "$image_tags_committed" -eq 0; then
    restore_prior_mutable_image_tag \
      chummer-run-api:local "$prior_portal_image_tag_id" || cleanup_failed=1
    restore_prior_mutable_image_tag \
      chummer-install-linking-postgres-tool:local \
      "$prior_postgres_tool_image_tag_id" || cleanup_failed=1
  fi
  if test -n "${cf_access_header_file:-}"; then
    rm -f -- "$cf_access_header_file" || cleanup_failed=1
  fi
  release_cutover_lease || cleanup_failed=1
  if test "$cleanup_failed" -eq 1; then exit 70; fi
  exit "$cleanup_status"
}

trap cutover_cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

source_preflight_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-public-edge-source-preflight.XXXXXX.json")"
overlay_publish_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-public-edge-overlay-publish.XXXXXX.json")"
overlay_activation_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-public-edge-overlay-activation.XXXXXX.json")"
prebuild_overlay_preflight_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-public-edge-overlay-prebuild.XXXXXX.json")"
overlay_preflight_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-public-edge-overlay-preflight.XXXXXX.json")"
postdeploy_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-public-edge-postdeploy.XXXXXX.json")"
postdeploy_artifact_dir="$(mktemp -d \
  "${RUNBOOK_LOG_DIR}/chummer-public-edge-browser-proofs.XXXXXX")"
chmod 600 "$source_preflight_receipt" "$overlay_publish_receipt" \
  "$overlay_activation_receipt" \
  "$prebuild_overlay_preflight_receipt" "$overlay_preflight_receipt" \
  "$postdeploy_receipt"

# This source pass deliberately skips only the stale active-overlay comparison so a replacement
# candidate can be built. The publisher verifies the staged candidate, and source is revalidated
# after the image build; the active overlay is checked immediately after activation while drained.
timeout --kill-after=10s 180s \
  python3 scripts/check_public_edge_deploy_preflight.py \
  --source-root "$source_root" --skip-overlay-marker-check \
  --runtime-proof-bind-source-sha256 "$CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256" \
  --release-channel-receipt "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256" \
  --output "$source_preflight_receipt"

# Build and verify a candidate under the staging root. This command deliberately does not select
# it as the active bind source, so a build or post-build source-preflight failure is live-safe.
timeout --kill-after=30s 3000s \
  python3 scripts/publish_public_edge_portal_overlay.py \
  --source-root "$source_root" --active-root "$active_root" \
  --staging-root "${overlay_base}-next/app" \
  --backup-root "${overlay_base}-backups" \
  --build-root "${overlay_base}-build" \
  --release-channel-receipt "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256" \
  --output "$overlay_publish_receipt"

# Compose sees the same exported roots with higher precedence than `.env`. The publisher has
# already bound the staged candidate to this source fingerprint.
prior_portal_image_tag_id="$(resolve_mutable_image_tag_id chummer-run-api:local)" || {
  echo "Could not query the prior chummer-run-api:local image tag." >&2
  exit 78
}
if test -n "$prior_portal_image_tag_id"; then
  require_full_image_id "$prior_portal_image_tag_id" || exit 78
fi
prior_postgres_tool_image_tag_id="$(resolve_mutable_image_tag_id \
  chummer-install-linking-postgres-tool:local)" || {
  echo "Could not query the prior chummer-install-linking-postgres-tool:local image tag." >&2
  exit 78
}
if test -n "$prior_postgres_tool_image_tag_id"; then
  require_full_image_id "$prior_postgres_tool_image_tag_id" || exit 78
fi
# Either build target can retag before Compose reports a failure, so rollback authority is active
# before the multi-service build begins.
image_tag_rollback_active=1
/usr/bin/timeout --kill-after=30s 3600s \
  "${docker_command[@]}" compose --env-file "$canonical_env_file" -p chummer6-hub \
  -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
  build --builder default chummer-portal chummer-install-linking-postgres-admin
candidate_portal_image_id="$(/usr/bin/timeout --kill-after=5s 30s "${docker_command[@]}" image inspect \
  chummer-run-api:local --format '{{.Id}}')" || exit 78
require_full_image_id "$candidate_portal_image_id" || exit 78
candidate_postgres_tool_image_id="$(/usr/bin/timeout --kill-after=5s 30s "${docker_command[@]}" image inspect \
  chummer-install-linking-postgres-tool:local --format '{{.Id}}')" || exit 78
require_full_image_id "$candidate_postgres_tool_image_id" || exit 78

timeout --kill-after=10s 180s \
  python3 scripts/check_public_edge_deploy_preflight.py \
  --source-root "$source_root" --skip-overlay-marker-check \
  --runtime-proof-bind-source-sha256 "$CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256" \
  --release-channel-receipt "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256" \
  --output "$prebuild_overlay_preflight_receipt"

cutover_drained=1
/usr/bin/timeout --kill-after=10s 60s \
  "${docker_command[@]}" compose --env-file "$canonical_env_file" -p chummer6-hub \
  -f docker-compose.public-edge.yml stop chummer-run-cloudflared

/usr/bin/timeout --kill-after=10s 60s \
  "${docker_command[@]}" compose --env-file "$canonical_env_file" -p chummer6-hub \
  -f docker-compose.public-edge.yml stop chummer-portal

assert_no_operator_jobs

# Resolve the already verified staging tree into the active path only while the old bind-mounted
# portal is stopped. Reuse rechecks the recorded source fingerprint and activation is atomic.
timeout --kill-after=30s 1800s \
  python3 scripts/publish_public_edge_portal_overlay.py --activate --reuse-staging \
  --shared-mutation-lock-token "$cutover_lock_token" \
  --source-root "$source_root" --active-root "$active_root" \
  --staging-root "${overlay_base}-next/app" \
  --backup-root "${overlay_base}-backups" \
  --build-root "${overlay_base}-build" \
  --release-channel-receipt "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256" \
  --output "$overlay_activation_receipt"

timeout --kill-after=10s 180s \
  python3 scripts/check_public_edge_deploy_preflight.py \
  --source-root "$source_root" --overlay-root "$active_root" \
  --runtime-proof-bind-source-sha256 "$CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256" \
  --release-channel-receipt "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256" \
  --output "$overlay_preflight_receipt"

assert_no_operator_jobs
operator_jobs_started=1
postgres_boundary_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-install-linking-postgres-boundary.XXXXXX.json")"
prepare_operator_log="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-install-linking-prepare.XXXXXX.log")"
local_store_probe_log="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-install-linking-local-store-probe.XXXXXX.log")"
import_operator_log="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-install-linking-import.XXXXXX.log")"
validate_operator_log="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-install-linking-validate.XXXXXX.log")"
chmod 600 "$postgres_boundary_receipt" "$prepare_operator_log" \
  "$local_store_probe_log" \
  "$import_operator_log" "$validate_operator_log"
local_install_linking_store_presence="$(probe_local_install_linking_store_presence \
  chummer-install-linking-postgres-import \
  "chummer6-hub-${cutover_id}-local-store-probe" "$local_store_probe_log")" || {
  echo "Could not prove whether a protected local install-linking store exists." >&2
  exit 78
}
case "$local_install_linking_store_presence" in
  present|absent) ;;
  *) echo "The local install-linking store probe returned an invalid disposition." >&2; exit 78 ;;
esac
assert_no_operator_jobs
/usr/bin/python3 -I scripts/materialize_install_linking_cutover_boundary.py \
  --output "$postgres_boundary_receipt" --phase prepare_starting \
  --cutover-id "$cutover_id" --candidate-image-id "$candidate_portal_image_id" \
  --candidate-tool-image-id "$candidate_postgres_tool_image_id" \
  --active-build-info "$active_build_info" >/dev/null

prepare_operator_image_id="$(run_operator_job_and_verify_image \
  chummer-install-linking-postgres-admin \
  "chummer6-hub-${cutover_id}-prepare" "$prepare_operator_log" prepare)"
/usr/bin/python3 -I scripts/materialize_install_linking_cutover_boundary.py \
  --output "$postgres_boundary_receipt" --phase prepare_completed \
  --cutover-id "$cutover_id" --candidate-image-id "$candidate_portal_image_id" \
  --candidate-tool-image-id "$candidate_postgres_tool_image_id" \
  --operator-container-image-id "$prepare_operator_image_id" \
  --active-build-info "$active_build_info" >/dev/null
assert_no_operator_jobs

# Import exactly once when the non-mutating probe proved that protected local store or floor state is
# present. A fresh deployment records the explicit no-local-store branch and proceeds directly to
# authority validation; it must never invoke import-local against a missing store.
if test "$local_install_linking_store_presence" = present; then
  import_operator_image_id="$(run_operator_job_and_verify_image \
    chummer-install-linking-postgres-import \
    "chummer6-hub-${cutover_id}-import" "$import_operator_log" \
    import-local --confirm-empty-authority)"
  /usr/bin/python3 -I scripts/materialize_install_linking_cutover_boundary.py \
    --output "$postgres_boundary_receipt" --phase import_completed \
    --cutover-id "$cutover_id" --candidate-image-id "$candidate_portal_image_id" \
    --candidate-tool-image-id "$candidate_postgres_tool_image_id" \
    --operator-container-image-id "$import_operator_image_id" \
    --active-build-info "$active_build_info" >/dev/null
else
  /usr/bin/python3 -I scripts/materialize_install_linking_cutover_boundary.py \
    --output "$postgres_boundary_receipt" --phase import_skipped_no_local_store \
    --cutover-id "$cutover_id" --candidate-image-id "$candidate_portal_image_id" \
    --candidate-tool-image-id "$candidate_postgres_tool_image_id" \
    --active-build-info "$active_build_info" >/dev/null
fi
assert_no_operator_jobs

validate_operator_image_id="$(run_operator_job_and_verify_image \
  chummer-install-linking-postgres-admin \
  "chummer6-hub-${cutover_id}-validate" "$validate_operator_log" validate)"
/usr/bin/python3 -I scripts/materialize_install_linking_cutover_boundary.py \
  --output "$postgres_boundary_receipt" --phase validate_completed \
  --cutover-id "$cutover_id" --candidate-image-id "$candidate_portal_image_id" \
  --candidate-tool-image-id "$candidate_postgres_tool_image_id" \
  --operator-container-image-id "$validate_operator_image_id" \
  --active-build-info "$active_build_info" >/dev/null
assert_no_operator_jobs
operator_jobs_started=0

/usr/bin/timeout --kill-after=10s 240s \
  "${docker_command[@]}" compose --env-file "$canonical_env_file" -p chummer6-hub \
  -f docker-compose.public-edge.yml up -d --no-deps --force-recreate \
  --wait --wait-timeout 180 chummer-portal

container_build_info_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-install-linking-container-build-info.XXXXXX.json")"
chmod 600 "$container_build_info_receipt"
/usr/bin/timeout --kill-after=5s 30s \
  "${docker_command[@]}" compose --env-file "$canonical_env_file" -p chummer6-hub \
  -f docker-compose.public-edge.yml exec -T chummer-portal \
  cat /app/.codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json \
  >"$container_build_info_receipt"
python3 scripts/validate_install_linking_cutover_overlay_binding.py \
  --preflight-receipt "$overlay_preflight_receipt" \
  --container-build-info-receipt "$container_build_info_receipt" \
  --source-root "$source_root" --active-root "$active_root" \
  --not-before-utc "$cutover_started_at"

readiness_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-install-linking-readiness.XXXXXX.json")"
chmod 600 "$readiness_receipt"
/usr/bin/timeout --kill-after=5s 30s \
  "${docker_command[@]}" compose --env-file "$canonical_env_file" -p chummer6-hub \
  -f docker-compose.public-edge.yml exec -T chummer-portal \
  curl --fail --silent --show-error --max-time 10 \
  --header 'Host: chummer.run' http://127.0.0.1:8080/api/ready \
  >"$readiness_receipt"
python3 scripts/validate_install_linking_cutover_readiness.py \
  --receipt "$readiness_receipt" --expected-build-info "$active_build_info" \
  --not-before-utc "$cutover_started_at"

/usr/bin/timeout --kill-after=10s 240s \
  "${docker_command[@]}" compose --env-file "$canonical_env_file" -p chummer6-hub \
  -f docker-compose.public-edge.yml up -d --no-deps --force-recreate \
  --wait --wait-timeout 180 \
  chummer-run-cloudflared

public_readiness_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-install-linking-public-readiness.XXXXXX.json")"
chmod 600 "$public_readiness_receipt"
case "${CODEXLIZ_CF_ACCESS_CLIENT_ID}${CODEXLIZ_CF_ACCESS_CLIENT_SECRET}" in
  *$'\r'*|*$'\n'*) echo "Cloudflare Access credentials contain a forbidden line break." >&2; exit 78 ;;
esac
cf_access_header_file="$(mktemp \
  "${RUNBOOK_LOG_DIR}/chummer-cf-access-headers.XXXXXX")"
chmod 600 "$cf_access_header_file"
printf 'CF-Access-Client-Id: %s\nCF-Access-Client-Secret: %s\n' \
  "$CODEXLIZ_CF_ACCESS_CLIENT_ID" "$CODEXLIZ_CF_ACCESS_CLIENT_SECRET" \
  >"$cf_access_header_file"
timeout --kill-after=5s 60s \
  curl --fail --silent --show-error --retry 5 --retry-all-errors --retry-delay 2 \
  --connect-timeout 5 --max-time 10 --header 'Cache-Control: no-cache' \
  --header "@$cf_access_header_file" \
  https://chummer.run/api/ready >"$public_readiness_receipt"
python3 scripts/validate_install_linking_cutover_readiness.py \
  --receipt "$public_readiness_receipt" --expected-build-info "$active_build_info" \
  --not-before-utc "$cutover_started_at"
rm -f -- "$cf_access_header_file"
cf_access_header_file=""

timeout --kill-after=30s 1800s \
  /usr/bin/python3 -I scripts/verify_public_edge_postdeploy_gate.py \
  --base-url https://chummer.run \
  --strict-preflight \
  --release-channel-receipt "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT" \
  --overlay-root "$active_root" \
  --expected-build-info "$active_build_info" \
  --require-downloads-status-playwright \
  --require-mobile-pwa-viewport-playwright \
  --require-frontdoor-navigation-playwright \
  --playwright-artifact-dir "$postdeploy_artifact_dir/downloads-status" \
  --mobile-pwa-viewport-artifact-dir "$postdeploy_artifact_dir/mobile-pwa-viewport" \
  --frontdoor-navigation-artifact-dir "$postdeploy_artifact_dir/frontdoor-navigation" \
  --output "$postdeploy_receipt"

accepted_portal_container_id="$(/usr/bin/timeout --kill-after=5s 30s \
  "${docker_command[@]}" compose --env-file "$canonical_env_file" -p chummer6-hub \
  -f docker-compose.public-edge.yml ps --all -q chummer-portal)"
case "$accepted_portal_container_id" in ""|*$'\n'*) exit 78 ;; esac
test "$(/usr/bin/timeout --kill-after=5s 30s \
  "${docker_command[@]}" container inspect --format '{{.Image}}' "$accepted_portal_container_id")" \
  = "$candidate_portal_image_id"
test "$(resolve_mutable_image_tag_id chummer-run-api:local)" = "$candidate_portal_image_id"
test "$(resolve_mutable_image_tag_id chummer-install-linking-postgres-tool:local)" \
  = "$candidate_postgres_tool_image_id"

/usr/bin/python3 -I scripts/materialize_install_linking_cutover_boundary.py \
  --output "$postgres_boundary_receipt" --phase public_acceptance_completed \
  --cutover-id "$cutover_id" --candidate-image-id "$candidate_portal_image_id" \
  --candidate-tool-image-id "$candidate_postgres_tool_image_id" \
  --active-build-info "$active_build_info" >/dev/null
image_tags_committed=1
cutover_drained=0
trap - HUP INT TERM
release_cutover_lease
trap - EXIT
echo "Source preflight receipt: $source_preflight_receipt"
echo "Closed Compose runtime receipt: $compose_runtime_attestation_receipt"
echo "Shared mutation lease receipt: $cutover_lease_receipt"
echo "Overlay publish receipt: $overlay_publish_receipt"
echo "Overlay activation receipt: $overlay_activation_receipt"
echo "Pre-build overlay fingerprint receipt: $prebuild_overlay_preflight_receipt"
echo "Overlay fingerprint receipt: $overlay_preflight_receipt"
echo "Container build-info receipt: $container_build_info_receipt"
echo "Local readiness receipt: $readiness_receipt"
echo "Public readiness receipt: $public_readiness_receipt"
echo "Browser-backed postdeploy receipt: $postdeploy_receipt"
echo "Irreversible PostgreSQL boundary receipt: $postgres_boundary_receipt"
echo "Local install-linking store disposition: $local_install_linking_store_presence"
echo "Local install-linking store probe log: $local_store_probe_log"
echo "Prepare operator log: $prepare_operator_log"
echo "Import operator log: $import_operator_log"
echo "Validate operator log: $validate_operator_log"
echo "Browser-backed postdeploy artifacts: $postdeploy_artifact_dir"
)
```

### Authenticated manual stale-lock recovery

The shared mutation lock never expires automatically. A failed acquisition remains a hard stop.
Only after an operator has used the process supervisor and Docker inventory to prove that no deploy,
restore, overlay activation, PostgreSQL operator job, or cutover shell still runs may the operator
recover the exact inspected lock. Run the recovery from the same clean-shell launcher boundary.
Independently select and verify the recovery tool SHA-256 before executing it.

```bash
lock_dir=/docker/chummercomplete/.state/public-edge-mutation.lock
recovery_tool=/docker/chummercomplete/chummer.run-services/scripts/recover_public_edge_mutation_lock.py
recovery_receipt_root=/docker/chummercomplete/.state/public-edge-lock-recovery-receipts
# Select the matching durable authorization file left by the interrupted lease receipt. Its name is
# `<actor>-<sha256-of-token>.owner-token` under the canonical recovery receipt root. Never copy,
# rename, print, or reconstruct it from the fixed lock.
: "${PUBLIC_EDGE_STALE_LOCK_AUTHORIZATION_FILE:?Export the matching persistent owner-token file}"
authorization_file="$PUBLIC_EDGE_STALE_LOCK_AUTHORIZATION_FILE"
: "${CHUMMER_PUBLIC_EDGE_LOCK_RECOVERY_TOOL_SHA256:?Export the independently selected tool SHA-256}"
[[ "$CHUMMER_PUBLIC_EDGE_LOCK_RECOVERY_TOOL_SHA256" =~ ^[0-9a-f]{64}$ ]]
test "$(/usr/bin/sha256sum -- "$recovery_tool" | /usr/bin/awk '{print $1}')" \
  = "$CHUMMER_PUBLIC_EDGE_LOCK_RECOVERY_TOOL_SHA256"
/usr/bin/install -d -m 0700 -- "$recovery_receipt_root"
test ! -L "$recovery_receipt_root"
test "$(/usr/bin/stat -c %a -- "$recovery_receipt_root")" = 700
test ! -L "$authorization_file"
test "$(/usr/bin/stat -c %a -- "$authorization_file")" = 600

# The capability was fsynced outside the lock before any Compose render/build mutation. Never print
# or recreate it from the stale lock: the external copy is the recovery authorization.
recovery_suffix="$(/usr/bin/date -u +%Y%m%dT%H%M%SZ)"

read -r lock_device lock_inode lock_mtime_ns < <(
  /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
    /usr/bin/python3 -I -c \
    'import os,sys; s=os.lstat(sys.argv[1]); print(s.st_dev, s.st_ino, s.st_mtime_ns)' \
    "$lock_dir"
)
read -r authorization_device authorization_inode authorization_mtime_ns < <(
  /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
    /usr/bin/python3 -I -c \
    'import os,sys; s=os.lstat(sys.argv[1]); print(s.st_dev, s.st_ino, s.st_mtime_ns)' \
    "$authorization_file"
)
recovery_receipt="$recovery_receipt_root/recovery-$recovery_suffix.json"
test ! -e "$recovery_receipt"
/usr/bin/timeout --kill-after=5s 60s \
  /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
  /usr/bin/python3 -I "$recovery_tool" \
  --owner-token-file "$authorization_file" \
  --expected-lock-device "$lock_device" \
  --expected-lock-inode "$lock_inode" \
  --expected-lock-mtime-ns "$lock_mtime_ns" \
  --expected-authorization-device "$authorization_device" \
  --expected-authorization-inode "$authorization_inode" \
  --expected-authorization-mtime-ns "$authorization_mtime_ns" \
  --minimum-age-seconds 900 \
  --reason "Interrupted public-edge mutation was manually inspected and is no longer running" \
  --confirm REMOVE_STALE_PUBLIC_EDGE_MUTATION_LOCK \
  --operator-attestation I_VERIFIED_NO_PUBLIC_EDGE_MUTATION_IS_RUNNING \
  --output "$recovery_receipt"
```

The tool first fsyncs an `in_progress` mode-`0600` receipt, rechecks the inspected lock and token
identities, atomically retires only a lock containing that authenticated owner token, removes the
external authorization, and then atomically fsyncs the `pass` receipt. It records only the token
digest, never the capability. A mismatched
identity, young lock, extra entry, missing manual attestation, or receipt error leaves recovery
failed closed. Preserve incomplete receipts for incident review.

Crash artifacts that no longer occupy the fixed lock are nonblocking but must not be deleted by
hand. For a digest-bound `.public-edge-mutation.lock.staging.<digest>` or
`.public-edge-mutation.lock.retired.<digest>` directory, inspect and capture the exact directory and
authorization device/inode/mtime values, then run the same clean command with `--mode orphan`,
`--orphan-path`, all three `--expected-artifact-*` values, and
`--confirm REMOVE_ORPHANED_PUBLIC_EDGE_MUTATION_ARTIFACT`. Omit `--orphan-path` and all artifact
identity flags only for an authorization-only orphan. For a legacy empty fixed lock with no
`owner-token`, use `--mode incomplete-lock`, the fixed-lock and authorization identities, and
`--confirm REMOVE_INCOMPLETE_PUBLIC_EDGE_MUTATION_LOCK`. These modes accept only the exact closed
partial shapes, retain the same minimum-age and no-active-mutation attestation, fsync an
`in_progress` receipt before removal, and produce a separate `pass` receipt. Any unexpected entry,
digest mismatch, identity drift, or nonempty tokenless fixed lock remains a hard stop.

The import service defaults to an invalid, non-mutating command. Never change that default: the
operator must supply both `import-local` and `--confirm-empty-authority`. The fixed host lock is held
from preflight through public restoration; a stale lock fails closed for operator review. The tunnel
must remain stopped until `compose up --wait` has accepted the portal health check and the separate
in-container `/api/ready` response passes the current deep-readiness contract, including the
`install_linking_store` check. A second validated receipt through the canonical public URL proves
the restored tunnel path through the governed Cloudflare Access service token. The final
browser-backed postdeploy gate remains inside the same mutation lock and drained rollback boundary.
`prepare` and `import-local` are durable PostgreSQL commits, not operations the shell can reverse.
The boundary receipt is written before `prepare` starts and advanced after each durable phase. Each
phase also gets a caller-owned mode-`0600` append-only journal file chained to the exact digest of
the previous phase. Every phase binds both the portal image ID and PostgreSQL tool image ID, and the
prepare/import/validate phases additionally bind the inspected image ID of the completed named
operator container before that container is removed. Until
public acceptance it names PostgreSQL PITR or governed recovery as the only rollback authority and
forbids rewinding the local mirror. Its machine-readable recovery mode is
`postgres_pitr_or_governed_recovery`; automatic database rollback, local-mirror rollback, and schema
or generation rewind remain false. Rollback is activated before the two-image Compose build; both
the portal and PostgreSQL tool tags are restored to their exact prior IDs on any failure. Neither
mutable image tag is committed until final acceptance passes. Archive all receipts, phase journals,
and the three operator logs; never delete or rewrite the phase journal files. All receipt and log
files are mode `0600`. Inspect portal logs after traffic is restored.

Back up the PostgreSQL service with tested point-in-time recovery and retain the Data Protection key
ring, its PKCS#12 wrapping certificate, and password under separate controlled custody. The database
stores protected envelopes; neither a database backup nor the key ring is independently sufficient.
Run restore drills that recover both to a segregated environment and validate before use.

Rollback is fail-closed. If prepare, import, or validate fails, leave the tunnel and portal stopped.
If startup or readiness fails, stop the portal again and leave the tunnel stopped; do not remove the
protected local floor, switch back to the local mirror, relax TLS, or grant the runtime role migrator
privileges. A database restored behind the local floor must remain unavailable until the
matching/newer PITR point is restored or a governed recovery is completed. Preserve the failed
authority and logs for diagnosis.


## Mode A: Filesystem Deploy (shared mount)

Repository variables:
1. `CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR`
2. `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL`

Local release path:
1. Build the release bundle on the controlled release host.
2. If `CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR` is configured, run `RUNBOOK_MODE=downloads-sync` to deploy the bundle after generation.
3. `scripts/publish-download-bundle.sh` prunes superseded desktop artifacts from the target downloads root before syncing the freshly built bundle.
4. The runbook verifies the local deployed manifest and live manifest URL.

Manual path:
1. `RUNBOOK_MODE=downloads-sync DOWNLOAD_BUNDLE_DIR=<bundleDir> DOWNLOAD_DEPLOY_DIR=<deployDir> DOWNLOADS_SYNC_DEPLOY_MODE=1 DOWNLOADS_SYNC_VERIFY_TARGET=<portalBaseOrManifestUrl> bash scripts/runbook.sh`
2. `RUNBOOK_MODE=downloads-verify DOWNLOADS_VERIFY_LINKS=1 DOWNLOADS_VERIFY_TARGET=<portalBaseOrManifestUrl> bash scripts/runbook.sh`
3. `RUNBOOK_MODE=downloads-smoke bash scripts/runbook.sh`

## Mode B: Object Storage Deploy (S3/R2 compatible)

Repository variables:
1. `CHUMMER_PORTAL_DOWNLOADS_S3_URI`
2. `CHUMMER_PORTAL_DOWNLOADS_S3_LATEST_URI` (optional)
3. `CHUMMER_PORTAL_DOWNLOADS_S3_ENDPOINT_URL` (optional; required for many R2/S3-compatible endpoints)
4. `CHUMMER_PORTAL_DOWNLOADS_S3_REGION` (optional, defaults to `us-east-1`)
5. `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL`

Repository secrets:
1. `CHUMMER_PORTAL_DOWNLOADS_AWS_ACCESS_KEY_ID`
2. `CHUMMER_PORTAL_DOWNLOADS_AWS_SECRET_ACCESS_KEY`
3. `CHUMMER_PORTAL_DOWNLOADS_AWS_SESSION_TOKEN` (optional)

Local release path:
1. Build the release bundle on the controlled release host.
2. If `CHUMMER_PORTAL_DOWNLOADS_S3_URI` is configured, run `RUNBOOK_MODE=downloads-sync-s3` to deploy the bundle after generation.
3. The runbook syncs the bundle using `scripts/publish-download-bundle-s3.sh`.
4. The runbook verifies the live manifest URL.

Manual path:
1. `RUNBOOK_MODE=downloads-sync-s3 DOWNLOAD_BUNDLE_DIR=<bundleDir> CHUMMER_PORTAL_DOWNLOADS_S3_URI=<s3://bucket/path> CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL=<portalBaseOrManifestUrl> [CHUMMER_PORTAL_DOWNLOADS_S3_ENDPOINT_URL=<endpoint>] bash scripts/runbook.sh`
2. `RUNBOOK_MODE=downloads-verify DOWNLOADS_VERIFY_LINKS=1 DOWNLOADS_VERIFY_TARGET=<portalBaseOrManifestUrl> bash scripts/runbook.sh`

## Daily Rolling Shelf

Use this path for the normal Windows/Linux rolling shelf:

1. Build only the platform artifacts required for the current verification pass.
2. Stage the downloads bundle.
3. Publish with `RUNBOOK_MODE=publish-latest-nightly bash scripts/runbook.sh`.

The command is guarded by the 08:00 Europe/Vienna release window and by the once-per-day shelf rule. Use an explicit emergency override only when the release owner accepts the extra publish.

## Mode C: Live `chummer.run` HTTP Publish

Use this mode when the public site must expose both the rebuilt downloads shelf and the new proof/deep-link controller routes.

Repository variables:
1. `CHUMMER_RELEASE_UPLOAD_TOKEN`
2. `CHUMMER_RELEASE_UPLOAD_URL` (optional; defaults to `https://chummer.run/api/internal/releases/bundles`)
3. `CHUMMER_RELEASE_UPLOAD_SESSIONS_URL` (optional; defaults to `https://chummer.run/api/internal/releases/upload-sessions`)
4. `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` (optional; defaults to `https://chummer.run/downloads/RELEASE_CHANNEL.generated.json`)
5. `CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_COUNT` (optional; defaults to `3`)
6. `CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_DELAY_SECONDS` (optional; defaults to `2`)
7. `CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_MAX_SAMPLES` (optional; defaults to `6`)

Required live sequence:
1. Deploy the updated public edge app first so the proof routes exist. The release authority must
   independently select the exact merged commit, verifier digest, release-receipt digest, and
   candidate runtime-proof digest. Do not derive any expected value from the checkout, receipt, or
   proof path being executed. In particular, `CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256`
   is a required external authority input, not a value the deploy may obtain by hashing the live bind
   source. Place its one-line lowercase digest in an operator-owned, symlink-free mode-`0400` file
   outside the checkout, verify that file's custody, and pass the value explicitly through the
   otherwise empty `env -i` environment:
```bash
runtime_proof_authority=/docker/chummercomplete/.state/public-edge-deploy-authority/runtime-proof-bind-source.sha256
test -f "$runtime_proof_authority" && test ! -L "$runtime_proof_authority"
test "$(/usr/bin/stat -c %a -- "$runtime_proof_authority")" = 400
test "$(/usr/bin/stat -c %u -- "$runtime_proof_authority")" = "$(/usr/bin/id -u)"
IFS= read -r approved_runtime_proof_sha256 < "$runtime_proof_authority"
[[ "$approved_runtime_proof_sha256" =~ ^[0-9a-f]{64}$ ]]

/usr/bin/env -i \
  PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
  CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1 \
  CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD='<externally-approved-40-hex-merged-commit>' \
  CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF='refs/remotes/origin/main' \
  CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256='5f9b25d9d2ce75e35542834cca9041eb373f2ff7aded5c21801d97b835bb5290' \
  CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT=/docker/chummercomplete/chummer-hub-registry/.codex-studio/published/RELEASE_CHANNEL.generated.json \
  CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256='<externally-approved-lowercase-sha256>' \
  CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256="$approved_runtime_proof_sha256" \
  CHUMMER_RUN_SERVICES_SOURCE=/docker/chummercomplete/chummer.run-services \
  /usr/bin/bash --noprofile --norc \
  /docker/chummercomplete/chummer.run-services/scripts/deploy_public_edge_portal.sh

unset approved_runtime_proof_sha256
```
   - Do not use raw `docker compose ... up -d --build chummer-portal` for release publication. The guarded wrapper source-gates the audited checkout, builds `chummer-run-api:local` from explicit contexts, runs the volume initializer, starts a uniquely named blue/green candidate with `--no-build`, and postdeploy-gates its exact image id before durably committing the candidate authority. The exact old portal is retained for rollback until that commit.
   - If a durable transaction journal exists, the wrapper reconciles it and exits without starting a new deploy. Rerun the deploy only after that recovery succeeds. To request idempotent reconciliation explicitly, repeat the authority-file checks above and use the same clean launcher, source-authority inputs, and explicit proof authority (release-receipt inputs are not required for recovery):
```bash
runtime_proof_authority=/docker/chummercomplete/.state/public-edge-deploy-authority/runtime-proof-bind-source.sha256
test -f "$runtime_proof_authority" && test ! -L "$runtime_proof_authority"
test "$(/usr/bin/stat -c %a -- "$runtime_proof_authority")" = 400
test "$(/usr/bin/stat -c %u -- "$runtime_proof_authority")" = "$(/usr/bin/id -u)"
IFS= read -r approved_runtime_proof_sha256 < "$runtime_proof_authority"
[[ "$approved_runtime_proof_sha256" =~ ^[0-9a-f]{64}$ ]]

/usr/bin/env -i \
  PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
  CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1 \
  CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD='<externally-approved-40-hex-merged-commit>' \
  CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF='refs/remotes/origin/main' \
  CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256='5f9b25d9d2ce75e35542834cca9041eb373f2ff7aded5c21801d97b835bb5290' \
  CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256="$approved_runtime_proof_sha256" \
  CHUMMER_RUN_SERVICES_SOURCE=/docker/chummercomplete/chummer.run-services \
  /usr/bin/bash --noprofile --norc \
  /docker/chummercomplete/chummer.run-services/scripts/deploy_public_edge_portal.sh recover

unset approved_runtime_proof_sha256
```
   An exact-identity or old-proof-mount failure returns `70` and keeps the journal for investigation.
2. Verify the live bootstrap matches the deployed source and the legacy path redirects cleanly:
`bash scripts/verify-live-mac-bootstrap.sh`
3. For a Mac release runner, open `https://chummer.run/downloads/release-upload` in a signed-in browser, copy the generated `Command` block, and paste that exact command into the Mac shell. That generated command includes the short-lived upload ticket; do not run the raw `bootstrap.sh` URL for promotion because it has no upload credential.
4. Rebuild the current unified shelf bundle:
`bash scripts/materialize-public-downloads-bundle.sh`
5. Upload the rebuilt bundle to the live shelf:
`RUNBOOK_MODE=downloads-upload-http DOWNLOAD_BUNDLE_DIR=/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads bash scripts/runbook.sh`
   - If `CHUMMER_RELEASE_UPLOAD_TOKEN` is unset, the upload step now prompts for it with hidden input instead of requiring an inline shell assignment.
   - Canonical post-publish success is gated on stable public truth, not one transient read. `scripts/public_download_shelf_truth_gate.py` now cache-busts the live shelf and requires repeated consecutive matches against the local `releases.json` and `RELEASE_CHANNEL.generated.json` before the publish lane can pass.
   - Keep the default `3` consecutive live matches unless you are intentionally relaxing the guard for a non-canonical environment. Set `CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION=1` only if you intentionally want `releases.json` compatibility drift to fail the run.

Public-edge source and browser proof gate:
1. Release-ready must prove the public-edge source before it can claim a deployable edge. `scripts/verify_chummer6_release_ready.sh` runs `scripts/verify_public_edge_deploy_source.py` before the Windows visual audit.
2. The source gate fails when the deploy tree is dirty, untracked, behind upstream, or when `docker-compose.public-edge.yml` builds `chummer-portal` from a different source path than the audited checkout.
3. For live portal publication, use the exact clean launcher in the required live sequence above.
   A plain shell invocation, a self-derived `HEAD`, or a caller-selected Docker/Compose route is not
   deployment authority and is intentionally rejected.
4. When compose defaults point at machine-local paths, pin the audited source explicitly:
`CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT=/docker/chummercomplete CHUMMER_RUN_SERVICES_CONTEXT_DIR=chummer.run-services CHUMMER_RUN_SERVICES_SOURCE=/docker/chummercomplete/chummer.run-services python3 scripts/verify_public_edge_deploy_source.py --repo-root /docker/chummercomplete/chummer.run-services --compose-file docker-compose.public-edge.yml --compose-service chummer-portal --require-upstream --json`
5. The public-edge postdeploy gate must include browser-backed evidence for release claims:
`python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --skip-preflight --require-downloads-status-playwright --require-mobile-pwa-viewport-playwright --require-frontdoor-navigation-playwright --output .codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
6. The browser receipts prove downloads/status, mobile viewport fit, and the Open Chummer Build/Play navigation; the same aggregate also verifies PWA static assets including manifest-declared icon/screenshot/shortcut paths and service-worker-declared cache/shell paths, the mobile ledger opt-in/no-store boundary for Black Ledger heat, followed-world updates, and session continuity, the service-worker non-interference boundary, ProductLift iframe shell, and ready-mobile handoff JSON plus its route-backed player/GM/organizer packet links.
7. If `/service-worker.js` is served from the play shell instead of the portal worker, treat the deploy as a failed public edge even when mobile routes load. The expected live boundary is `shared_portal_root_worker`.
8. On the release host, also pin the mutable local image tag to the approved portal image id:
`python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --skip-preflight --expected-portal-image-id sha256:<approved-portal-image-id> --portal-container chummer6-hub-chummer-portal-1 --portal-image-tag chummer-run-api:local --output .codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
This catches local `chummer-run-api:local` retags that can otherwise restore stale or dirty bytes while public routes still partially respond.
9. The same aggregate emits the `flagshipHorizons` child receipt documented in `docs/FLAGSHIP_HORIZONS_GATE.md`; release evidence should show `flagshipHorizonsStatus=pass` and `flagshipHorizonsBrowserProofCoverage=full`.
10. If the runtime image guard fails, restore the portal without rebuilding it, then rerun the same postdeploy gate:
```bash
/usr/bin/env -i \
  PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
  CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1 \
  /usr/bin/python3 -I \
  /docker/chummercomplete/chummer.run-services/scripts/restore_public_edge_portal_image.py \
  --expected-portal-image-id 'sha256:<approved-portal-image-id>' \
  --image-tag chummer-run-api:local \
  --include-image-tags-matching '^chummer-run-api:pwa-direct' \
  --include-image-tags-matching '^chummer-run-api:current-source' \
  --include-image-tags-matching '^chummer-run-api:fixed-alias' \
  --compose-file /docker/chummercomplete/chummer.run-services/docker-compose.public-edge.yml \
  --env-file /docker/chummercomplete/chummer.run-services/.env \
  --project-name chummer6-hub \
  --portal-container chummer6-hub-chummer-portal-1 \
  --base-url https://chummer.run \
  --expected-release-channel '<approved-channel>' \
  --stability-window-seconds 120 --stability-poll-seconds 10 \
  --require-all-browser-proofs \
  --playwright-artifact-dir /docker/chummercomplete/chummer.run-services/.codex-studio/published/public-edge-browser-proofs \
  --output /docker/chummercomplete/chummer.run-services/.codex-studio/published/PUBLIC_EDGE_PORTAL_IMAGE_RESTORE.generated.json
```
The restore command validates the approved image id, records Docker created time, tags, digests, and labels for any drifted image it replaces, repoints the configured mutable tag plus explicitly matched local aliases, runs `docker compose run --rm --no-deps chummer-portal-volume-init`, and only after that succeeds recreates `chummer-portal` with `docker compose up -d --no-build --no-deps --force-recreate`. It repairs bounded image drift during the optional stability window and retries the runtime image guard plus the downloads/status, mobile viewport, and Open Chummer navigation browser proofs in its postdeploy receipt while the container warms up.

Mac release bootstrap note:
1. The hosted mac bootstrap now defaults temporary packaging work to the run workspace and exports:
`CHUMMER_MAC_RELEASE_TMPDIR="$work_root/tmp"`
`CHUMMER_DESKTOP_INSTALLER_TMPDIR="$TMPDIR/desktop-installer"`
2. Override `CHUMMER_MAC_RELEASE_TMPDIR` when the default workspace volume is not the right SSD for `hdiutil` temp work.
3. Override `CHUMMER_DESKTOP_INSTALLER_TMPDIR` separately only when installer-image temp files must live on a different volume.
4. If a release ticket still fails with `hdiutil: create failed - No space left on device`, point `CHUMMER_MAC_RELEASE_TMPDIR` at a workspace-backed path on the target SSD and clear unneeded old `run-*` directories under the same parent before rerunning.

Dry run:
1. `CHUMMER_RELEASE_UPLOAD_DRY_RUN=1 RUNBOOK_MODE=downloads-upload-http DOWNLOAD_BUNDLE_DIR=/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads bash scripts/runbook.sh`

Required post-publish checks:
1. `https://chummer.run/downloads/RELEASE_CHANNEL.generated.json`
2. `https://chummer.run/downloads/install/avalonia-osx-arm64-installer`
3. `https://chummer.run/downloads/install/avalonia-win-x64-installer`
4. `https://chummer.run/downloads/proof/windows/current/artifacts/avalonia-win-x64-installer/installer`
5. `https://chummer.run/downloads/proof/windows/chummer-avalonia-win-x64-installer.exe`
6. `python3 scripts/public_download_shelf_truth_gate.py --base-url https://chummer.run --local-manifest /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/releases.json --local-canonical-manifest /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json`
   - Treat a publish as incomplete if the gate cannot prove the same promoted version on repeated live samples. A one-off match is not enough evidence for public truth.

Windows installer gold proof:
1. This proof is a native Windows visual/startup gate only. It must not publish downloads or promote a release.
2. Preferred remote path: run the native Windows proof runner from a controlled Windows host.
3. The runner captures the promoted installer startup receipt plus installer progress/completion screenshots, then exports a `windows-installer-gold-proof` bundle.
   Every bundle must contain both the native-Windows startup receipt and the visual-audit source plus its referenced screenshot bytes for the same promoted digest.
   Delivery must be a bounded zip whose proof tree includes `WINDOWS_INSTALLER_VISUAL_AUDIT.source.json`; loose folders and extra archive members are rejected.
4. Auto-captured screenshots are intentionally marked `review_required`; a human must inspect clipping/readability before changing those rows to `pass`.
5. Drop the exported zip into the ignored intake folder `.state/incoming_windows_installer_gold_proof/`, preferably named `windows-installer-gold-proof-<promoted-digest-prefix>.zip`.
6. Import the exported proof bundle from this repository root:
`python3 scripts/import_windows_installer_gold_proof_artifact.py windows-installer-gold-proof.zip --verify`
7. Refresh the current operator ask and digest-specific import command:
`python3 scripts/materialize_windows_installer_visual_audit_intake_request.py`
   - The current ask is written to `_completion/windows_installer_visual_audit/CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt`.
8. Watch for the bundle automatically from this repository root:
`python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --wait-seconds 900 --poll-seconds 10 --refresh-intake-request`
9. Local native-Windows fallback:
`scripts/capture_windows_installer_gold_proof.ps1 -LaunchInstaller -CaptureVisualAudit -ScaledDpiScale 1.5`
10. Manual screenshot fallback:
`scripts/capture_windows_installer_visual_audit.ps1 -LaunchInstaller -CaptureRequiredSet -ScaledDpiScale 1.5 -ClippingStatus pass -ReadabilityStatus pass`
11. Gold remains blocked until `scripts/verify_windows_installer_visual_audit.py` passes against the promoted installer digest.

Private Windows proof upload lane:
1. The durable proof shelf is mounted separately at `/windows-proof-store`; upload sessions use `/windows-proof-upload-sessions`. Neither path may overlap `/downloads-source`, which remains the canonical release shelf.
2. Keep `CHUMMER_WINDOWS_PROOF_UPLOAD_ENABLED=false` and `CHUMMER_WINDOWS_PROOF_CF_ACCESS_GATED=false` by default.
3. Confirm the Cloudflare Access policy covers the complete `/downloads/proof/windows` route family before setting both flags to `true` and recreating `chummer-portal`. Setting only one flag leaves the upload middleware unavailable.
4. Never publish proof bytes through `/downloads/supplemental/windows`, `/downloads/install/{artifactId}/proof`, or other aliases outside the protected route family.

Manifest-driven public route proof:
1. `python3 scripts/verify_public_routes_from_manifest.py --base-url https://chummer.run --manifest .codex-design/product/PUBLIC_LANDING_MANIFEST.yaml --output .codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
2. Local reverse-proxy variant: `python3 scripts/verify_public_routes_from_manifest.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --manifest .codex-design/product/PUBLIC_LANDING_MANIFEST.yaml --output .codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
3. The verifier checks public routes directly, checks anonymous fallbacks for registered routes without following the redirect, and emits a machine-readable JSON proof packet for publish or audit closeout.

Canonical domain posture:
1. `https://chummer.run` is the only hostname this runbook treats as publicly canonical and release-claimable.

## Strict Test Gate Commands (host-side)

Use these when you want hard failures instead of soft-skips.

Prerequisite probe:
1. `RUNBOOK_MODE=host-prereqs bash scripts/runbook.sh`

Single wrapper command:
1. `bash scripts/runbook-strict-host-gates.sh [optionalTestFilter] [optionalFramework]`
2. If no framework is provided, strict wrapper defaults to `net10.0` to keep host runs on the cross-platform test leg.
3. Local strict stage defaults to `FullyQualifiedName!~Chummer.Tests.ApiIntegrationTests&FullyQualifiedName!~Chummer.Tests.Presentation.DualHeadAcceptanceTests&FullyQualifiedName!~Chummer.Tests.ChummerTest`; override with `TEST_LOCAL_FILTER` when needed.
4. Wrapper fails when tracked `git` worktree state changes during the run; set `STRICT_ALLOW_WORKTREE_DRIFT=1` only when this is intentionally expected.

Local tests:
1. `RUNBOOK_MODE=local-tests TEST_NUGET_SOFT_FAIL=0 TEST_DISABLE_BUILD_SERVERS=1 TEST_MAX_CPU=1 bash scripts/runbook.sh`
2. Optional offline attempt after successful restore cache: `RUNBOOK_MODE=local-tests TEST_NO_RESTORE=1 TEST_DISABLE_BUILD_SERVERS=1 TEST_MAX_CPU=1 bash scripts/runbook.sh`

Docker tests:
1. `RUNBOOK_MODE=docker-tests DOCKER_TESTS_SOFT_FAIL=0 DOCKER_TESTS_BUILD=1 bash scripts/runbook.sh`

## Expected Verification Outcome

1. `/downloads/releases.json` has `downloads` with at least one artifact.
2. `version` is not `"unpublished"` in deployment mode.
3. When `CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS=true` (or `DOWNLOADS_VERIFY_LINKS=1`), each artifact URL/file in manifest verification is reachable.
4. Portal `/downloads/` renders artifact links that return HTTP 200.
5. When the bundle ships `proof/windows`, the deployed shelf exposes both the proof dispatch routes and the direct proof files exclusively below the Cloudflare Access-gated `/downloads/proof/windows` boundary. Public `/downloads/install/{artifactId}` routes may dispatch users to that boundary but must never serve proof-store bytes themselves.

## Portal Status Meanings

The portal manifest/page now distinguishes operator states explicitly:

1. `published`: real self-hosted artifacts are available.
2. `unpublished`: manifest is intentionally empty; no builds have been published yet.
3. `manifest-empty`: manifest exists but lists zero artifacts; treat this as a deployment/manifest generation problem.
4. `manifest-missing`: portal cannot find the self-hosted manifest or local artifacts.
5. `manifest-error`: portal found `releases.json` but could not parse it.
6. `fallback-source`: portal is using `CHUMMER_PORTAL_DOWNLOADS_FALLBACK_URL` instead of self-hosted artifacts.

Operational expectation:

1. Production/self-hosted deploys should end in `published`.
2. `unpublished` is acceptable only before the first release or in local-dev output that intentionally keeps the repo fallback snapshot.
3. `manifest-empty`, `manifest-missing`, and `manifest-error` should be treated as operator failures, not user-facing “normal empty state”.
4. Published portal builds do not ship the checked-in `Chummer.Portal/downloads/releases.json` snapshot, so a missing storage mount should surface as `manifest-missing`, not as a fake `unpublished` release feed.
