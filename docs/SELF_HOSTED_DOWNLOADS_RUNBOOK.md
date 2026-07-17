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
4. Optional unattended overrides:
`RUNBOOK_LOG_DIR` pins runbook log files to a known writable directory and `RUNBOOK_STATE_DIR` pins writable state (for example `DOTNET_CLI_HOME`) to a known writable directory.

## Public-edge mutable storage preflight

The portal process remains non-root and defaults to UID/GID `1654:1654`. The governed deploy and restore paths first stop the prior portal writer, then run `chummer-portal-volume-init` from the same local app image, and only recreate the portal after initialization succeeds. If initialization or recreation fails, they attempt to restart the exact prior container and fall back to its immutable image when Compose has already removed it. The Compose service dependency still requires successful initialization during normal startup. This one-shot service has no network, a read-only root filesystem, `no-new-privileges`, all capabilities dropped except `CHOWN`, `SETUID`, and `SETGID`, and no secret mounts. It migrates the four named mutable roots (`chummer-run-api-state`, `chummer-release-upload-sessions`, `chummer-windows-proof-store`, and `chummer-windows-proof-upload-sessions`) and then creates and removes an owner-only probe as the configured portal identity. Symlinks and special files in those roots fail the preflight.

`/downloads-source` is a host bind, not a named volume. The initializer only creates and removes a probe there; it never changes host ownership or modes. Before deployment, the operator must grant the configured portal identity create, write, and delete access. Choose one governed host-side policy and verify it locally, for example:

```bash
# Simple dedicated-owner policy.
sudo chown -R 1654:1654 /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads

# Or preserve the current owner and grant an access/default ACL.
sudo setfacl -Rm u:1654:rwX,d:u:1654:rwX /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads
```

Do not make the downloads tree world-writable. If `CHUMMER_PORTAL_UID` or `CHUMMER_PORTAL_GID` changes, rebuild the app image with the matching Docker build arguments and update the host ownership/ACL before recreating the portal.

The read-only data-protection certificate, certificate-password file, and InstallLinking PostgreSQL runtime connection file are also outside the initializer's authority. On the host, each must be explicitly readable by the configured UID/GID while remaining inaccessible to other users (normally portal-owned mode `0400`, or a narrowly scoped ACL on a root-owned mode `0600` file). Never mount these files into the initializer. The guarded deploy wrapper and image-restore tool abort before portal recreation if the volume preflight fails.

The guarded deploy wrapper runs the strict public-edge source preflight and `docker compose config --quiet` before `buildx` can retag the local image. The latter makes the required PKCS#12, password-file, PostgreSQL credential, runtime-role, and release-shelf posture inputs fail before any build or portal quiesce. After the one-shot initializer, Compose waits for the portal `/api/ready` healthcheck; the wrapper then requires `/api/ready/publication`, which additionally proves layout-v1 activation and the configured release-storage free-space admission thresholds. The replacement stays transactional through the full browser-backed postdeploy gate. Any failure stops the replacement and restores both the prior running portal image and the exact prior mutable image tag; a failed rollback exits distinctly with status `70`.

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
this exact drain/stop/activate/prepare/import/validate/start/prove/restore order. Staging does not
change the active overlay. Activation happens only after the currently bind-mounted portal is
stopped. Keep Cloudflare Tunnel and the portal stopped for the whole database-administration window
so public traffic cannot reach a partially cut-over instance and the portal's local writer lease
cannot race the one-time import. Every operator job is bounded by the outer `timeout`; the tool has
no permission to turn an unbounded wait into a successful cutover.

```bash
(
set -euo pipefail
umask 077

: "${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT:?Export the selected release-channel receipt path}"
: "${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256:?Export its independently selected SHA-256}"
: "${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL:?Export public_stable, stable, preview, or nightly}"
: "${CHUMMER_RUN_SERVICES_SOURCE:?Export the absolute run-services source root used by Compose}"
: "${CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT:?Export the absolute public-edge Docker build context}"
: "${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR:?Export the absolute portal /app overlay root used by Compose}"
: "${CODEXLIZ_CF_ACCESS_CLIENT_ID:?Export the governed Cloudflare Access client id}"
: "${CODEXLIZ_CF_ACCESS_CLIENT_SECRET:?Export the governed Cloudflare Access client secret}"

normalize_existing_root() {
  root_label="$1"
  root_value="$2"
  timeout --kill-after=5s 15s python3 - "$root_label" "$root_value" <<'PY'
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

# Acquire the one shared host mutation lock before even resolving Compose. Deploy, restore, and
# database cutover all use this exact non-overridable authority.
if test -L /docker/chummercomplete/.state; then
  echo "The shared public-edge mutation lock root must not be a symlink." >&2
  exit 78
fi
install -d -m 700 -- /docker/chummercomplete/.state
if ! test -d /docker/chummercomplete/.state \
  || test -L /docker/chummercomplete/.state \
  || test "$(stat -c %u /docker/chummercomplete/.state)" -ne "$(id -u)" \
  || test "$(stat -c %a /docker/chummercomplete/.state)" != 700; then
  echo "The shared public-edge mutation lock root must be caller-owned mode 0700." >&2
  exit 78
fi
cutover_lock_dir=/docker/chummercomplete/.state/public-edge-mutation.lock
if ! mkdir -m 700 -- "$cutover_lock_dir"; then
  echo "Another public-edge mutation is active, or its stale lock requires operator review." >&2
  exit 75
fi
cutover_lock_token_file="$cutover_lock_dir/owner-token"
cutover_lock_token="$(python3 -I -S -c 'import secrets; print(secrets.token_hex(32))')"
(umask 077; set -o noclobber; printf '%s\n' "$cutover_lock_token" >"$cutover_lock_token_file")
chmod 600 -- "$cutover_lock_token_file"
cutover_drained=0
operator_jobs_started=0
portal_image_tag_mutated=0
portal_image_tag_committed=0
prior_portal_image_tag_id=""
cf_access_header_file=""

release_initial_cutover_lock() {
  initial_status=$?
  trap - EXIT HUP INT TERM
  rm -f -- "$cutover_lock_token_file"
  if ! rmdir -- "$cutover_lock_dir"; then exit 70; fi
  exit "$initial_status"
}
trap release_initial_cutover_lock EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Resolve Compose while holding the mutation lock. Stream the rendered configuration directly to
# the verifier because it can contain secrets; persist only this non-secret root-binding receipt.
compose_root_attestation_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-compose-root-binding.XXXXXX.json")"
chmod 600 "$compose_root_attestation_receipt"
timeout --kill-after=5s 60s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
  config --format json |
  timeout --kill-after=5s 30s \
  python3 /dev/fd/3 "$source_root" "$active_root" "$build_context" \
  3<<'PY' >"$compose_root_attestation_receipt"
import json
import sys

expected_source, expected_overlay, expected_build_context = sys.argv[1:]
try:
    payload = json.load(sys.stdin)
except (OSError, ValueError) as error:
    raise SystemExit(f"Compose root-binding config is not valid JSON: {error}") from error

services = payload.get("services")
if not isinstance(services, dict):
    raise SystemExit("Compose root-binding config has no services object")

source_services = (
    "chummer-run-identity",
    "chummer-portal",
    "chummer-install-linking-postgres-admin",
    "chummer-install-linking-postgres-import",
)
expected_builds = {
    "chummer-portal": (f"{expected_source}/Chummer.Run.Api/Dockerfile", ""),
    "chummer-install-linking-postgres-admin": (
        f"{expected_source}/Chummer.Run.Api/Dockerfile",
        "install-linking-postgres-tool-final",
    ),
    "chummer-install-linking-postgres-import": (
        f"{expected_source}/Chummer.Run.Api/Dockerfile",
        "install-linking-postgres-tool-final",
    ),
}
resolved_sources = {}
resolved_builds = {}
for service_name in source_services:
    service = services.get(service_name)
    build = service.get("build") if isinstance(service, dict) else None
    contexts = build.get("additional_contexts") if isinstance(build, dict) else None
    actual = contexts.get("run-services-source") if isinstance(contexts, dict) else None
    if actual != expected_source:
        raise SystemExit(
            f"Compose resolved {service_name} run-services-source as {actual!r}, "
            f"not {expected_source!r}"
        )
    resolved_sources[service_name] = actual
    if service_name in expected_builds:
        expected_dockerfile, expected_target = expected_builds[service_name]
        actual_context = build.get("context") if isinstance(build, dict) else None
        actual_dockerfile = build.get("dockerfile") if isinstance(build, dict) else None
        actual_target = build.get("target") if isinstance(build, dict) else None
        actual_target = actual_target if isinstance(actual_target, str) else ""
        if (
            actual_context != expected_build_context
            or actual_dockerfile != expected_dockerfile
            or actual_target != expected_target
        ):
            raise SystemExit(
                f"Compose resolved {service_name} build binding as "
                f"context={actual_context!r}, dockerfile={actual_dockerfile!r}, "
                f"target={actual_target!r}; expected context={expected_build_context!r}, "
                f"dockerfile={expected_dockerfile!r}, target={expected_target!r}"
            )
        resolved_builds[service_name] = {
            "context": actual_context,
            "dockerfile": actual_dockerfile,
            "target": actual_target,
        }

portal = services.get("chummer-portal")
volumes = portal.get("volumes") if isinstance(portal, dict) else None
app_binds = [
    volume
    for volume in volumes or []
    if isinstance(volume, dict) and volume.get("target") == "/app"
]
if len(app_binds) != 1:
    raise SystemExit("Compose must resolve exactly one chummer-portal /app mount")
app_bind = app_binds[0]
if (
    app_bind.get("type") != "bind"
    or app_bind.get("source") != expected_overlay
    or app_bind.get("read_only") is not True
):
    raise SystemExit("Compose chummer-portal /app bind does not match the selected read-only overlay")

json.dump(
    {
        "contractName": "chummer.install_linking.compose_root_binding.v1",
        "status": "pass",
        "runServicesSource": expected_source,
        "portalAppOverlay": expected_overlay,
        "sourceContextServices": resolved_sources,
        "sourceBuildServices": resolved_builds,
        "portalAppBindReadOnly": True,
    },
    sys.stdout,
    indent=2,
    sort_keys=True,
)
sys.stdout.write("\n")
PY

overlay_base="${active_root%/app}"
active_build_info="$active_root/.codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
cutover_started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

operator_job_ids() {
  admin_job_ids="$(timeout --kill-after=5s 15s docker ps -aq \
    --filter label=com.docker.compose.project=chummer6-hub \
    --filter label=com.docker.compose.service=chummer-install-linking-postgres-admin)" || return
  import_job_ids="$(timeout --kill-after=5s 15s docker ps -aq \
    --filter label=com.docker.compose.project=chummer6-hub \
    --filter label=com.docker.compose.service=chummer-install-linking-postgres-import)" || return
  if test -n "$admin_job_ids"; then printf '%s\n' "$admin_job_ids"; fi
  if test -n "$import_job_ids"; then printf '%s\n' "$import_job_ids"; fi
}

stop_operator_jobs() {
  operator_job_ids 2>/dev/null | while IFS= read -r container_id; do
    if test -n "$container_id"; then
      timeout --kill-after=5s 20s docker rm --force "$container_id" \
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

resolve_portal_image_tag_id() {
  resolved_ids="$(timeout --kill-after=5s 30s docker image ls --quiet --no-trunc \
    --filter reference=chummer-run-api:local)" || return
  resolved_ids="$(printf '%s\n' "$resolved_ids" | awk 'NF && !seen[$0]++')"
  case "$resolved_ids" in *$'\n'*) return 1 ;; esac
  printf '%s' "$resolved_ids"
}

restore_prior_portal_image_tag() {
  current_portal_image_tag_id="$(resolve_portal_image_tag_id)" || return
  if test -n "$prior_portal_image_tag_id"; then
    if test "$current_portal_image_tag_id" != "$prior_portal_image_tag_id"; then
      timeout --kill-after=5s 30s docker tag \
        "$prior_portal_image_tag_id" chummer-run-api:local || return
    fi
  elif test -n "$current_portal_image_tag_id"; then
    timeout --kill-after=5s 30s docker image rm chummer-run-api:local >/dev/null || return
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
    timeout --kill-after=10s 60s \
      docker compose --env-file .env -p chummer6-hub \
      -f docker-compose.public-edge.yml \
      stop chummer-run-cloudflared chummer-portal >/dev/null 2>&1 || cleanup_failed=1
  fi
  if test "$portal_image_tag_mutated" -eq 1 \
    && test "$portal_image_tag_committed" -eq 0; then
    restore_prior_portal_image_tag || cleanup_failed=1
  fi
  if test -n "${cf_access_header_file:-}"; then
    rm -f -- "$cf_access_header_file" || cleanup_failed=1
  fi
  rm -f -- "$cutover_lock_token_file" || cleanup_failed=1
  rmdir -- "$cutover_lock_dir" >/dev/null 2>&1 || cleanup_failed=1
  if test "$cleanup_failed" -eq 1; then exit 70; fi
  exit "$cleanup_status"
}

trap cutover_cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

source_preflight_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-public-edge-source-preflight.XXXXXX.json")"
overlay_publish_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-public-edge-overlay-publish.XXXXXX.json")"
overlay_activation_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-public-edge-overlay-activation.XXXXXX.json")"
prebuild_overlay_preflight_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-public-edge-overlay-prebuild.XXXXXX.json")"
overlay_preflight_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-public-edge-overlay-preflight.XXXXXX.json")"
postdeploy_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-public-edge-postdeploy.XXXXXX.json")"
postdeploy_artifact_dir="$(mktemp -d \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-public-edge-browser-proofs.XXXXXX")"
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
prior_portal_image_tag_id="$(resolve_portal_image_tag_id)" || {
  echo "Could not query the prior chummer-run-api:local image tag." >&2
  exit 78
}
case "$prior_portal_image_tag_id" in
  ""|sha256:*) ;;
  *) echo "The prior portal image tag did not resolve to a SHA-256 image id." >&2; exit 78 ;;
esac
timeout --kill-after=30s 3600s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
  build chummer-portal chummer-install-linking-postgres-admin
portal_image_tag_mutated=1
candidate_portal_image_id="$(timeout --kill-after=5s 30s docker image inspect \
  chummer-run-api:local --format '{{.Id}}')" || exit 78
case "$candidate_portal_image_id" in
  sha256:*) ;;
  *) echo "The candidate portal image tag did not resolve to a SHA-256 image id." >&2; exit 78 ;;
esac

timeout --kill-after=10s 180s \
  python3 scripts/check_public_edge_deploy_preflight.py \
  --source-root "$source_root" --skip-overlay-marker-check \
  --output "$prebuild_overlay_preflight_receipt"

cutover_drained=1
timeout --kill-after=10s 60s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml stop chummer-run-cloudflared

timeout --kill-after=10s 60s \
  docker compose --env-file .env -p chummer6-hub \
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
  --output "$overlay_preflight_receipt"

assert_no_operator_jobs
operator_jobs_started=1
postgres_boundary_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-install-linking-postgres-boundary.XXXXXX.json")"
chmod 600 "$postgres_boundary_receipt"
/usr/bin/python3 -I scripts/materialize_install_linking_cutover_boundary.py \
  --output "$postgres_boundary_receipt" --phase prepare_starting \
  --cutover-id "$cutover_started_at" --candidate-image-id "$candidate_portal_image_id" \
  --active-build-info "$active_build_info" >/dev/null

timeout --kill-after=10s 180s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
  run --rm chummer-install-linking-postgres-admin prepare
/usr/bin/python3 -I scripts/materialize_install_linking_cutover_boundary.py \
  --output "$postgres_boundary_receipt" --phase prepare_completed \
  --cutover-id "$cutover_started_at" --candidate-image-id "$candidate_portal_image_id" \
  --active-build-info "$active_build_info" >/dev/null
assert_no_operator_jobs

# Run this import exactly once only when migrating an existing protected local store into an
# empty PostgreSQL authority. Omit it for a fresh deployment. The explicit flag is mandatory.
timeout --kill-after=10s 180s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
  run --rm chummer-install-linking-postgres-import \
  import-local --confirm-empty-authority
/usr/bin/python3 -I scripts/materialize_install_linking_cutover_boundary.py \
  --output "$postgres_boundary_receipt" --phase import_completed \
  --cutover-id "$cutover_started_at" --candidate-image-id "$candidate_portal_image_id" \
  --active-build-info "$active_build_info" >/dev/null
assert_no_operator_jobs

timeout --kill-after=10s 180s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
  run --rm chummer-install-linking-postgres-admin validate
/usr/bin/python3 -I scripts/materialize_install_linking_cutover_boundary.py \
  --output "$postgres_boundary_receipt" --phase validate_completed \
  --cutover-id "$cutover_started_at" --candidate-image-id "$candidate_portal_image_id" \
  --active-build-info "$active_build_info" >/dev/null
assert_no_operator_jobs
operator_jobs_started=0

timeout --kill-after=10s 240s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml up -d --no-deps --force-recreate \
  --wait --wait-timeout 180 chummer-portal

container_build_info_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-install-linking-container-build-info.XXXXXX.json")"
chmod 600 "$container_build_info_receipt"
timeout --kill-after=5s 30s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml exec -T chummer-portal \
  cat /app/.codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json \
  >"$container_build_info_receipt"
python3 scripts/validate_install_linking_cutover_overlay_binding.py \
  --preflight-receipt "$overlay_preflight_receipt" \
  --container-build-info-receipt "$container_build_info_receipt" \
  --source-root "$source_root" --active-root "$active_root" \
  --not-before-utc "$cutover_started_at"

readiness_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-install-linking-readiness.XXXXXX.json")"
chmod 600 "$readiness_receipt"
timeout --kill-after=5s 30s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml exec -T chummer-portal \
  curl --fail --silent --show-error --max-time 10 \
  --header 'Host: chummer.run' http://127.0.0.1:8080/api/ready \
  >"$readiness_receipt"
python3 scripts/validate_install_linking_cutover_readiness.py \
  --receipt "$readiness_receipt" --expected-build-info "$active_build_info" \
  --not-before-utc "$cutover_started_at"

timeout --kill-after=10s 240s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml up -d --no-deps --force-recreate \
  --wait --wait-timeout 180 \
  chummer-run-cloudflared

public_readiness_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-install-linking-public-readiness.XXXXXX.json")"
chmod 600 "$public_readiness_receipt"
case "${CODEXLIZ_CF_ACCESS_CLIENT_ID}${CODEXLIZ_CF_ACCESS_CLIENT_SECRET}" in
  *$'\r'*|*$'\n'*) echo "Cloudflare Access credentials contain a forbidden line break." >&2; exit 78 ;;
esac
cf_access_header_file="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-cf-access-headers.XXXXXX")"
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

accepted_portal_container_id="$(timeout --kill-after=5s 30s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml ps --all -q chummer-portal)"
case "$accepted_portal_container_id" in ""|*$'\n'*) exit 78 ;; esac
test "$(timeout --kill-after=5s 30s \
  docker container inspect --format '{{.Image}}' "$accepted_portal_container_id")" \
  = "$candidate_portal_image_id"
test "$(resolve_portal_image_tag_id)" = "$candidate_portal_image_id"

/usr/bin/python3 -I scripts/materialize_install_linking_cutover_boundary.py \
  --output "$postgres_boundary_receipt" --phase public_acceptance_completed \
  --cutover-id "$cutover_started_at" --candidate-image-id "$candidate_portal_image_id" \
  --active-build-info "$active_build_info" >/dev/null
portal_image_tag_committed=1
cutover_drained=0
trap - HUP INT TERM
rm -f -- "$cutover_lock_token_file"
rmdir -- "$cutover_lock_dir"
trap - EXIT
echo "Source preflight receipt: $source_preflight_receipt"
echo "Compose root-binding receipt: $compose_root_attestation_receipt"
echo "Overlay publish receipt: $overlay_publish_receipt"
echo "Overlay activation receipt: $overlay_activation_receipt"
echo "Pre-build overlay fingerprint receipt: $prebuild_overlay_preflight_receipt"
echo "Overlay fingerprint receipt: $overlay_preflight_receipt"
echo "Container build-info receipt: $container_build_info_receipt"
echo "Local readiness receipt: $readiness_receipt"
echo "Public readiness receipt: $public_readiness_receipt"
echo "Browser-backed postdeploy receipt: $postdeploy_receipt"
echo "Irreversible PostgreSQL boundary receipt: $postgres_boundary_receipt"
echo "Browser-backed postdeploy artifacts: $postdeploy_artifact_dir"
)
```

The import service defaults to an invalid, non-mutating command. Never change that default: the
operator must supply both `import-local` and `--confirm-empty-authority`. The fixed host lock is held
from preflight through public restoration; a stale lock fails closed for operator review. The tunnel
must remain stopped until `compose up --wait` has accepted the portal health check and the separate
in-container `/api/ready` response passes the current deep-readiness contract, including the
`install_linking_store` check. A second validated receipt through the canonical public URL proves
the restored tunnel path through the governed Cloudflare Access service token. The final
browser-backed postdeploy gate remains inside the same mutation lock and drained rollback boundary.
`prepare` and `import-local` are durable PostgreSQL commits, not operations the shell can reverse.
The boundary receipt is written before `prepare` starts and advanced after each durable phase; until
public acceptance it names PostgreSQL PITR or governed recovery as the only rollback authority and
forbids rewinding the local mirror. Its machine-readable recovery mode is
`postgres_pitr_or_governed_recovery`; automatic database rollback, local-mirror rollback, and schema
or generation rewind remain false. The mutable portal image tag is not committed until that final
acceptance passes. Archive all eleven
mode-`0600` receipts and inspect portal logs after traffic
is restored.

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
1. Deploy the updated public edge app first so the proof routes exist:
`CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD="$(git rev-parse HEAD)" CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM=1 bash scripts/deploy_public_edge_portal.sh`
   - Do not use raw `docker compose ... up -d --build chummer-portal` for release publication. The guarded wrapper source-gates the audited checkout, builds `chummer-run-api:local` from explicit contexts, runs the volume initializer, recreates `chummer-portal` with `--no-build`, and postdeploy-gates the exact image id before the deploy is considered publishable.
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
3. For live portal publication, prefer the guarded deploy wrapper:
`CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD="$(git rev-parse HEAD)" CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM=1 bash scripts/deploy_public_edge_portal.sh`
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
`python3 scripts/restore_public_edge_portal_image.py --expected-portal-image-id sha256:<approved-portal-image-id> --image-tag chummer-run-api:local --include-image-tags-matching '^chummer-run-api:pwa-direct' --include-image-tags-matching '^chummer-run-api:current-source' --include-image-tags-matching '^chummer-run-api:fixed-alias' --compose-file docker-compose.public-edge.yml --env-file .env --project-name chummer6-hub --portal-container chummer6-hub-chummer-portal-1 --base-url https://chummer.run --stability-window-seconds 120 --stability-poll-seconds 10 --require-all-browser-proofs --playwright-artifact-dir .codex-studio/published/public-edge-browser-proofs --output .codex-studio/published/PUBLIC_EDGE_PORTAL_IMAGE_RESTORE.generated.json`
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
