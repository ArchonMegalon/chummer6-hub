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
3. Use preapproved runbook/script paths from repository root (`/docker/chummercomplete`).
4. Optional unattended overrides:
`RUNBOOK_LOG_DIR` pins runbook log files to a known writable directory and `RUNBOOK_STATE_DIR` pins writable state (for example `DOTNET_CLI_HOME`) to a known writable directory.
5. Before an install-linking authority cutover, explicitly export
`CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT` as the selected canonical release-channel receipt path
and `CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256` as its independently selected SHA-256.
These are non-secret evidence selectors and are intentionally not inferred from Compose's `.env`.

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

Build both current images, then perform the cutover in this exact
drain/stop/prepare/import/validate/start/prove/restore order. Keep Cloudflare Tunnel and the portal
stopped for the whole administrative window so public traffic cannot reach a partially cut-over
instance and the portal's local writer lease cannot race the one-time import. Every operator job is
bounded by the outer `timeout`; the tool has no permission to turn an unbounded wait into a
successful cutover.

```bash
(
set -euo pipefail
umask 077

: "${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT:?Export the selected release-channel receipt path}"
: "${CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256:?Export its independently selected SHA-256}"
: "${CHUMMER_RUN_SERVICES_SOURCE:?Export the absolute run-services source root used by Compose}"
: "${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR:?Export the absolute portal /app overlay root used by Compose}"

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
active_root="$(normalize_existing_root \
  CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR "$CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR")"
case "$active_root" in
  */app) ;;
  *) echo "The normalized portal overlay root must end in /app." >&2; exit 78 ;;
esac
export CHUMMER_RUN_SERVICES_SOURCE="$source_root"
export CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR="$active_root"

# Resolve Compose before any mutating Docker call. Stream the rendered configuration directly to
# the verifier because it can contain secrets; persist only this non-secret root-binding receipt.
compose_root_attestation_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-compose-root-binding.XXXXXX.json")"
chmod 600 "$compose_root_attestation_receipt"
timeout --kill-after=5s 60s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
  config --format json |
  timeout --kill-after=5s 30s \
  python3 /dev/fd/3 "$source_root" "$active_root" \
  3<<'PY' >"$compose_root_attestation_receipt"
import json
import sys

expected_source, expected_overlay = sys.argv[1:]
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
resolved_sources = {}
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

# One fixed deployment-scoped location prevents RUNBOOK_STATE_DIR overrides from creating
# independent locks for the same Compose project.
install -d -m 700 -- /docker/chummercomplete/chummer.run-services/.state
cutover_lock_dir=/docker/chummercomplete/chummer.run-services/.state/install-linking-postgres-cutover.lock
if ! mkdir -m 700 -- "$cutover_lock_dir"; then
  echo "Another cutover is active, or a stale lock requires operator review: $cutover_lock_dir" >&2
  exit 75
fi

cutover_drained=0
operator_jobs_started=0

operator_job_ids() {
  timeout --kill-after=5s 15s docker ps -aq \
    --filter label=com.docker.compose.project=chummer6-hub \
    --filter label=com.docker.compose.service=chummer-install-linking-postgres-admin
  timeout --kill-after=5s 15s docker ps -aq \
    --filter label=com.docker.compose.project=chummer6-hub \
    --filter label=com.docker.compose.service=chummer-install-linking-postgres-import
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

cutover_cleanup() {
  cleanup_status=$?
  trap - EXIT HUP INT TERM
  if test "$operator_jobs_started" -eq 1; then
    stop_operator_jobs
  fi
  if test "$cutover_drained" -eq 1; then
    timeout --kill-after=10s 60s \
      docker compose --env-file .env -p chummer6-hub \
      -f docker-compose.public-edge.yml \
      stop chummer-run-cloudflared chummer-run-cloudflared-replica \
      chummer-portal >/dev/null 2>&1 || true
  fi
  rmdir -- "$cutover_lock_dir" >/dev/null 2>&1 || true
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
prebuild_overlay_preflight_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-public-edge-overlay-prebuild.XXXXXX.json")"
overlay_preflight_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-public-edge-overlay-preflight.XXXXXX.json")"
chmod 600 "$source_preflight_receipt" "$overlay_publish_receipt" \
  "$prebuild_overlay_preflight_receipt" "$overlay_preflight_receipt"

# This pre-activation pass deliberately skips only the stale active-overlay comparison so a
# replacement overlay can be built. A full fingerprint check is mandatory below before drain.
timeout --kill-after=10s 180s \
  python3 scripts/check_public_edge_deploy_preflight.py \
  --source-root "$source_root" --skip-overlay-marker-check \
  --output "$source_preflight_receipt"

timeout --kill-after=30s 3000s \
  python3 scripts/publish_public_edge_portal_overlay.py --activate \
  --source-root "$source_root" --active-root "$active_root" \
  --staging-root "${overlay_base}-next/app" \
  --backup-root "${overlay_base}-backups" \
  --build-root "${overlay_base}-build" \
  --release-channel-receipt "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT" \
  --release-channel-receipt-sha256 "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256" \
  --output "$overlay_publish_receipt"

timeout --kill-after=10s 180s \
  python3 scripts/check_public_edge_deploy_preflight.py \
  --source-root "$source_root" --overlay-root "$active_root" \
  --output "$prebuild_overlay_preflight_receipt"

# Compose sees the same exported roots with higher precedence than `.env`. Building between two
# full fingerprint passes binds its named context to the unchanged source used by the overlay.
timeout --kill-after=30s 3600s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
  build chummer-portal chummer-install-linking-postgres-admin

timeout --kill-after=10s 180s \
  python3 scripts/check_public_edge_deploy_preflight.py \
  --source-root "$source_root" --overlay-root "$active_root" \
  --output "$overlay_preflight_receipt"

cutover_drained=1
timeout --kill-after=10s 60s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml \
  stop chummer-run-cloudflared chummer-run-cloudflared-replica

timeout --kill-after=10s 60s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml stop chummer-portal

assert_no_operator_jobs
operator_jobs_started=1
timeout --kill-after=10s 180s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
  run --rm chummer-install-linking-postgres-admin prepare
assert_no_operator_jobs

# Run this import exactly once only when migrating an existing protected local store into an
# empty PostgreSQL authority. Omit it for a fresh deployment. The explicit flag is mandatory.
timeout --kill-after=10s 180s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
  run --rm chummer-install-linking-postgres-import \
  import-local --confirm-empty-authority
assert_no_operator_jobs

timeout --kill-after=10s 180s \
  docker compose --env-file .env -p chummer6-hub \
  -f docker-compose.public-edge.yml --profile install-linking-postgres-admin \
  run --rm chummer-install-linking-postgres-admin validate
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
  chummer-run-cloudflared chummer-run-cloudflared-replica

public_readiness_receipt="$(mktemp \
  "${RUNBOOK_LOG_DIR:-/tmp}/chummer-install-linking-public-readiness.XXXXXX.json")"
chmod 600 "$public_readiness_receipt"
timeout --kill-after=5s 60s \
  curl --fail --silent --show-error --retry 5 --retry-all-errors --retry-delay 2 \
  --connect-timeout 5 --max-time 10 --header 'Cache-Control: no-cache' \
  https://chummer.run/api/ready >"$public_readiness_receipt"
python3 scripts/validate_install_linking_cutover_readiness.py \
  --receipt "$public_readiness_receipt" --expected-build-info "$active_build_info" \
  --not-before-utc "$cutover_started_at"

cutover_drained=0
trap - HUP INT TERM
rmdir -- "$cutover_lock_dir"
trap - EXIT
echo "Source preflight receipt: $source_preflight_receipt"
echo "Compose root-binding receipt: $compose_root_attestation_receipt"
echo "Overlay publish receipt: $overlay_publish_receipt"
echo "Pre-build overlay fingerprint receipt: $prebuild_overlay_preflight_receipt"
echo "Overlay fingerprint receipt: $overlay_preflight_receipt"
echo "Container build-info receipt: $container_build_info_receipt"
echo "Local readiness receipt: $readiness_receipt"
echo "Public readiness receipt: $public_readiness_receipt"
)
```

The import service defaults to an invalid, non-mutating command. Never change that default: the
operator must supply both `import-local` and `--confirm-empty-authority`. The fixed host lock is held
from preflight through public restoration; a stale lock fails closed for operator review. Every
tunnel replica must remain stopped until `compose up --wait` has accepted the portal health check
and the separate in-container `/api/ready` response passes the current deep-readiness contract,
including the `install_linking_store` check. A second validated receipt through the canonical public
URL proves the restored tunnel path. Archive all eight mode-`0600` receipts and inspect portal logs
after traffic is restored.

Back up the PostgreSQL service with tested point-in-time recovery and retain the Data Protection key
ring, its PKCS#12 wrapping certificate, and password under separate controlled custody. The database
stores protected envelopes; neither a database backup nor the key ring is independently sufficient.
Run restore drills that recover both to a segregated environment and validate before use.

Rollback is fail-closed. If prepare, import, or validate fails, leave every tunnel replica and the
portal stopped. If startup or readiness fails, stop the portal again and leave every tunnel replica
stopped; do not remove the protected local floor, switch back to the local mirror, relax TLS, or
grant the runtime role migrator privileges. A database restored behind the local floor must remain
unavailable until the matching/newer PITR point is restored or a governed recovery is completed.
Preserve the failed authority and logs for diagnosis.

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

1. Build and collect the complete authoritative shelf for the candidate version. A platform-scoped build may be used for local verification, but it is not a patch bundle for the live shelf.
2. Stage one downloads bundle containing every desktop install tuple that must remain published.
3. Publish with the implemented live shelf path:
`bash scripts/materialize-public-downloads-bundle.sh`
`RUNBOOK_MODE=downloads-upload-http DOWNLOAD_BUNDLE_DIR=/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads bash scripts/runbook.sh`
4. Verify a preview/nightly shelf with incomplete platform coverage using:
`CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0 RUNBOOK_MODE=downloads-verify DOWNLOADS_VERIFY_LINKS=1 DOWNLOADS_VERIFY_TARGET=https://chummer.run/downloads/RELEASE_CHANNEL.generated.json bash scripts/runbook.sh`
5. Keep the default strict verifier for gold promotion:
`RUNBOOK_MODE=downloads-verify DOWNLOADS_VERIFY_LINKS=1 DOWNLOADS_VERIFY_TARGET=https://chummer.run/downloads/RELEASE_CHANNEL.generated.json bash scripts/runbook.sh`

The preview verifier proves the manifest, live links, and honest `review_required` / `coverage_incomplete` posture. It must not be used to claim Stable or gold readiness while macOS, native Windows proof coverage, or browser-backed Google OAuth linking proof is missing.

Authoritative shelf rule:

1. Upload-session completion replaces the managed release shelf; it does not merge a platform-scoped bundle into the current shelf. The legacy direct-bundle endpoint is permanently disabled.
2. Promotion rejects an incoming bundle that omits any desktop install tuple already present in the canonical live manifest. Explicit scoped updates and explicit removals are not supported yet.
3. Chummer's minimum completion floor is always Avalonia on `linux/linux-x64`, `windows/win-x64`, and `macos/osx-arm64`. A partial first shelf is allowed only as an honestly incomplete preview and must remain `coverage_incomplete` / `review_required`.
4. Do not retain old platform rows while stamping them with a new version. Rebuild a coherent cross-platform candidate whose artifact bytes, startup-smoke receipts, proof, version, and publication time agree.
5. The filesystem and S3 publisher wrappers run the same tuple-loss preflight before generating or copying live manifests/files. A malformed or unreachable existing manifest fails closed; only an actually absent first shelf may bypass the comparison.

## Mode C: Live `chummer.run` HTTP Publish

Use this mode when the public site must expose both the rebuilt downloads shelf and the new proof/deep-link controller routes.

Repository variables:
1. `CHUMMER_RELEASE_UPLOAD_TOKEN`
2. `CHUMMER_RELEASE_UPLOAD_SESSIONS_URL` (optional; defaults to `https://chummer.run/api/internal/releases/upload-sessions`)
3. `CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK=0` (optional compatibility setting; `0` is the default and any true value is rejected because direct upload cannot produce a durable staged-session completion receipt)
4. `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` (optional; defaults to `https://chummer.run/downloads/RELEASE_CHANNEL.generated.json`)
5. `CHUMMER_RELEASE_UPLOAD_ATTEMPT_RECEIPT_PATH` (optional; defaults beside the release bundle/response to `release-upload-handoff.json` and must not name an unresolved prior attempt)
6. `CHUMMER_RELEASE_UPLOAD_MAX_RESPONSE_BYTES` (optional; defaults to `1048576`, bounds every upload API response transfer, and is clamped to 1 KiB-16 MiB)

Client recovery rule: the publisher atomically writes and fsyncs the non-secret handoff through `created`, `uploaded`, `request_started`, and `completed`. `request_started` means publication outcome is unknown even if curl observed a status or partial body. Never create a replacement session from that state. Use a current Fleet internal token to call `POST {sessionsUrl}/{sessionId}/reconcile`; an upload ticket, including a newly rotated ticket, cannot take over the old session. A `200` result completes the handoff, `activation-aborted` proves a durable abort, and `publication-outcome-unknown` remains reconcile-only. Archive a resolved receipt before starting a different candidate; the client refuses to overwrite it.

Release-upload ticket controls:
1. `CHUMMER_RELEASE_UPLOAD_TICKET_LIFETIME_MINUTES` controls ticket lifetime and is clamped to 10-720 minutes. The default is 720 minutes.
2. `CHUMMER_RELEASE_UPLOAD_TICKET_REVOCATION_EPOCH` selects the active global ticket epoch. Its default is `1`. Changing it invalidates every ticket issued under the previous value after every Hub replica restarts with the new configuration.
3. Every Hub replica that issues or validates release-upload tickets must use the same epoch and the same persistent ASP.NET Core Data Protection key ring (`CHUMMER_DATA_PROTECTION_KEYS_PATH`). A matching epoch alone is insufficient when replicas do not share keys.
4. Rotate the epoch as a coordinated deployment. Do not leave old- and new-epoch replicas serving concurrently: each side rejects tickets issued by the other, producing intermittent authorization failures behind a load balancer.
5. Treat an epoch change as global revocation. The server additionally binds each signed-in ticket to one staged upload session, reuses that session for safe setup retries, rejects a different ticket on its files/chunks/completion routes, rejects every direct bundle upload regardless of credential type, and records the completed result until the ticket expires so completion retries cannot publish again. Internal fleet automation tokens remain multi-session credentials on the staged-session routes only.
6. Never put a ticket value in a command line, task, log, receipt, shell history, or caller-visible environment assignment. Transfer it through a hidden prompt or a mode-`0600` credential file, keep it process-local only as long as needed, and delete the file and unset the value on every exit path. Rotation values are identifiers, not tickets; do not reuse a ticket as the epoch.
7. The first deployment of epoch-aware ticket validation intentionally invalidates tickets issued by the legacy single-purpose protector. Issue fresh tickets only after all replicas are on the same epoch-aware version.
8. Use a new unique epoch for every rotation and never roll the configuration back to an earlier value. Reusing an old epoch can make an otherwise unexpired ticket cryptographically valid again; the retained single-session completion record is a second line of defense, not a substitute for monotonic epoch rotation or persistent shared session storage.
9. Configure `CHUMMER_RELEASE_UPLOAD_SESSION_ROOT` on persistent storage shared by every upload-serving replica. Ticket/session binding and idempotent completion are filesystem-backed; an ephemeral or replica-local root cannot provide cross-restart or cross-replica replay protection. Retain completed metadata until its ticket expiry and purge only afterward.

Required live sequence:
1. Export the independently selected canonical release-channel receipt path and SHA-256 as
`CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT` and
`CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256`. Then run the source/build-lane preflight:
`python3 scripts/check_public_edge_deploy_preflight.py --skip-overlay-marker-check --output /tmp/chummer-public-edge-source-preflight.json`
   - Skipping the active-overlay comparison is permitted only for this pre-activation replacement pass. A full fingerprint check is mandatory immediately after activation and before recreate.
   - The preflight receipt now includes `overlayBuildInfoSourceFingerprint`; fail closed if the active mounted overlay build-info is missing the fingerprint or if it does not match current source.
   - Foreign build lanes that are obviously stale for more than `86400` seconds are auto-ignored by default; the receipt reports them through `autoIgnoredStaleForeignLockCount` while still keeping local-scope or fresher foreign build activity blocking.
   - Treat the mounted overlay as current only when the receipt proves the overlay root and fingerprint together: `overlayRoot`, `overlayBuildInfoSourceFingerprint.aggregateMatchesCurrentSource`, `overlayBuildInfoSourceFingerprint.recordedAggregateSha256`, `overlayBuildInfoSourceFingerprint.expectedAggregateSha256`, `overlayBuildInfoSourceFingerprint.missingKeys`, and `overlayBuildInfoSourceFingerprint.mismatchedKeys`.
2. Stage, verify, and activate a fresh mounted `/app` payload from the current repo:
`python3 scripts/publish_public_edge_portal_overlay.py --activate --release-channel-receipt "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT" --release-channel-receipt-sha256 "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256" --output /tmp/chummer-public-edge-overlay-publish.json`
   - The public-edge compose service bind-mounts `/app` from `${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR}`. Rebuilding the image alone does not refresh the live runtime payload when that overlay is stale.
   - The overlay publish proof must now fail closed if `/` does not render the Play gate and the canonical `/#turn-runsite-card -> /mobile/player#turn-runsite-card` landing redirect from the staged payload.
   - The public canonical link is `/#turn-runsite-card`. The landing page still tolerates the malformed legacy fragment `/#turn-runsite-card?` for backward compatibility, but verification and receipts should emit the canonical link.
   - The staged proof now also boots the overlay with a local runtime stub for the public play proxy and hosted-board presence contract, then records `localLiveSurfaceParity`. Treat the overlay as verified only when that embedded parity receipt reports `status=pass` with `failureCount=0`.
   - Treat the overlay publish receipt as current only when it also reports `landingBrowserRedirectStatus=pass`, `landingBrowserRedirectExpectedPath=/mobile/player`, `landingBrowserRedirectExpectedHash=#turn-runsite-card`, `landingBrowserRedirectPathMatches=true`, and `landingBrowserRedirectHashMatches=true`.
   - If `dotnet publish` was interrupted after writing a valid staging tree, rerun with `--reuse-staging` and the same two release-channel binding arguments to reuse `${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR%/*}-next/app` instead of restarting the full publish.
3. Run the full preflight and require `overlayBuildInfoSourceFingerprint.aggregateMatchesCurrentSource=true` before recreate:
`python3 scripts/check_public_edge_deploy_preflight.py --output /tmp/chummer-public-edge-overlay-preflight.json`
   - Bind every later live proof to the independently attested active overlay. Run this from the canonical services source root after activation; the helper recomputes the digest from the current source and active payload instead of trusting `/api/ready` or the build-info assertion by itself:
   - The current staged payload fingerprint contract is `sha256-canonical-path-content-size-posix-mode-runtime-mount-exclusions-v3`. Its only byte exclusion is `wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json`, whose bytes are supplied by the dedicated read-only runtime mount.
   - That exclusion is byte-only: the staged mode receipt must still bind the proof path as exactly one regular `0644` file. Missing, replaced, linked, or mode-drifted mountpoints fail readiness.
   - Refresh the bind source with `scripts/materialize_hub_local_release_proof.py` before this full preflight (the canonical `scripts/ai/verify.sh` path does this automatically). The materializer atomically replaces both published and served proof artifacts as single-link regular `0644` files, including when proof bytes are unchanged; the caller's umask cannot relax that mode.
   - Treat a `0664`, linked, or non-regular proof source as a failed materialization. Rerun the canonical materializer; do not loosen the staged or runtime `0644` contract and do not rely on a manual `chmod` that later writers can undo.
   - Require `runtimeProofBindSource.status=pass`, `checks.regularFile=true`, `checks.singleLink=true`, and `checks.exactMode0644=true` in the full preflight receipt before recreating the portal. This checks the host bind source that Docker will actually mount, not only the attested placeholder inside the immutable overlay.
   - Runtime readiness re-hashes every other staged payload byte and verifies the complete path/kind/mode receipt against the active overlay. Any drift returns `503` until a newly attested overlay is activated; refreshing only the mounted proof bytes does not invalidate the immutable payload identity.
```bash
expected_build_info="${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR:?set the attested active overlay root}/.codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
expected_full_deployment_digest_sha256="$(
  python3 - "$expected_build_info" "${CHUMMER_RUN_SERVICES_SOURCE:-$PWD}" <<'PY'
import os
import sys
from pathlib import Path

from scripts.verify_public_edge_postdeploy_gate import load_expected_full_deployment_digest

build_info = Path(os.path.abspath(os.fspath(Path(sys.argv[1]).expanduser())))
print(
    load_expected_full_deployment_digest(
        build_info,
        source_root=Path(sys.argv[2]),
        overlay_root=build_info.parents[2],
    ),
    end="",
)
PY
)"
```
4. Recreate the public-edge portal service so it boots the refreshed mounted overlay:
`docker compose --env-file .env -p chummer6-hub -f docker-compose.public-edge.yml up -d --no-deps --force-recreate chummer-portal`
5. Verify the live bootstrap matches the deployed source and the legacy path redirects cleanly:
`bash scripts/verify-live-mac-bootstrap.sh`
6. For a Mac release runner, open `https://chummer.run/downloads/release-upload` in a signed-in browser, mint and copy a fresh short-lived access code, then copy the generated `Command` block into the Mac shell and paste the code only at its hidden prompt. The command, page source, bootstrap URL, and shell history must not contain the ticket. Do not run the raw `bootstrap.sh` URL for promotion because it has no upload credential or reviewed repository pins.
7. Rebuild the current unified shelf bundle:
`bash scripts/materialize-public-downloads-bundle.sh`
8. Upload the rebuilt bundle to the live shelf:
`CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK=0 RUNBOOK_MODE=downloads-upload-http DOWNLOAD_BUNDLE_DIR=/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads bash scripts/runbook.sh`
   - If `CHUMMER_RELEASE_UPLOAD_TOKEN` is unset, the upload step now prompts for it with hidden input instead of requiring an inline shell assignment.
   - Canonical post-publish success is gated on `RELEASE_CHANNEL.generated.json`. Set `CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION=1` only if you intentionally want `releases.json` compatibility drift to fail the run.
   - Artifact-factory autolaunch is now best-effort by default. Set `CHUMMER_ARTIFACT_FACTORY_AUTOLAUNCH_REQUIRED=1` only when a post-publish artifact-factory launch must be fatal for the release run.

Mac release bootstrap note:
1. The hosted mac bootstrap now defaults temporary packaging work to the run workspace and exports:
`CHUMMER_MAC_RELEASE_TMPDIR="$work_root/tmp"`
`CHUMMER_DESKTOP_INSTALLER_TMPDIR="$TMPDIR/desktop-installer"`
2. Override `CHUMMER_MAC_RELEASE_TMPDIR` when the default workspace volume is not the right SSD for `hdiutil` temp work.
3. Override `CHUMMER_DESKTOP_INSTALLER_TMPDIR` separately only when installer-image temp files must live on a different volume.
4. If a release ticket still fails with `hdiutil: create failed - No space left on device`, point `CHUMMER_MAC_RELEASE_TMPDIR` at a workspace-backed path on the target SSD and clear unneeded old `run-*` directories under the same parent before rerunning.
5. The Mac bootstrap produces a macOS-scoped verification bundle. It may prove the macOS lane, but it must not be treated as an incremental mutation of a healthy Linux/Windows/macOS authoritative shelf. Assemble and validate the complete cross-platform candidate before authoritative promotion.

Dry run:
1. `CHUMMER_RELEASE_UPLOAD_DRY_RUN=1 RUNBOOK_MODE=downloads-upload-http DOWNLOAD_BUNDLE_DIR=/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads bash scripts/runbook.sh`

Required post-publish checks:
1. `https://chummer.run/downloads/RELEASE_CHANNEL.generated.json`
2. `https://chummer.run/downloads/install/avalonia-win-x64-installer`
3. `https://chummer.run/downloads/file/avalonia-win-x64-installer`
4. `https://chummer.run/downloads/files/chummer-avalonia-win-x64-installer.exe`
5. Preview shelves may return 404 for `https://chummer.run/downloads/install/avalonia-osx-arm64-installer` and `https://chummer.run/downloads/install/avalonia-win-x64-installer/proof` until the missing macOS artifact and native Windows visual proof are captured.
6. Public-edge postdeploy gate after the rebuilt edge is live:
`python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --skip-preflight --expected-build-info "$expected_build_info" --expected-full-deployment-digest-sha256 "$expected_full_deployment_digest_sha256" --expected-pwa-asset-inventory-sha256 "$expected_pwa_asset_inventory_sha256" --output /tmp/chummer-public-edge-postdeploy-canonical.json`

Required gold promotion checks:
1. `RUNBOOK_MODE=downloads-verify DOWNLOADS_VERIFY_LINKS=1 DOWNLOADS_VERIFY_TARGET=https://chummer.run/downloads/RELEASE_CHANNEL.generated.json bash scripts/runbook.sh`
2. `https://chummer.run/downloads/install/avalonia-osx-arm64-installer`
3. `https://chummer.run/downloads/install/avalonia-win-x64-installer/proof`
4. `https://chummer.run/downloads/proof/windows/chummer-avalonia-win-x64-installer.exe`
5. `cd chummer.run-services && python3 scripts/materialize_google_oauth_linking_operator_evidence_request.py --base-url https://chummer.run && python3 scripts/verify_google_oauth_linking_operator_evidence_request.py`
6. `cd chummer.run-services && python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run && python3 scripts/verify_google_oauth_linking_proof.py --require-pass`

Windows installer gold proof:
1. This proof is a native Windows visual/startup gate only. It must not publish downloads or promote a release.
2. Preferred remote path: run the native Windows proof runner from a controlled Windows host.
3. The runner captures the promoted installer startup receipt plus installer progress/completion screenshots, then exports a `windows-installer-gold-proof` bundle.
4. Auto-captured screenshots are intentionally marked `review_required`; a human must inspect clipping/readability before changing those rows to `pass`.
5. Every bundle must contain both the native-Windows startup receipt and `Chummer.Portal/downloads/visual-audit/windows-installer/`, including `WINDOWS_INSTALLER_VISUAL_AUDIT.source.json`; previously published startup proof is not substituted into a new bundle.
6. Delivery must be a bounded zip in the ignored intake folder `.state/incoming_windows_installer_gold_proof/`, preferably named `windows-installer-gold-proof-<promoted-digest-prefix>.zip`.
7. Extracted-directory artifacts are rejected without inspection. This keeps the unattended watcher on one bounded, immutable intake format.
8. Import the exported proof bundle from this repository root:
`python3 scripts/import_windows_installer_gold_proof_artifact.py windows-installer-gold-proof.zip --intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --verify`
   - That `--verify` import reruns the full intake-request post-import gate chain; it does not stop after the first verifier.
9. The intake receipt prints the exact digest-specific import command:
`python3 scripts/materialize_windows_installer_visual_audit_intake_request.py`
10. Local native-Windows fallback:
`scripts/capture_windows_installer_gold_proof.ps1 -LaunchInstaller -CaptureVisualAudit -ScaledDpiScale 1.5`
11. Manual screenshot fallback:
`scripts/capture_windows_installer_visual_audit.ps1 -LaunchInstaller -CaptureRequiredSet -ScaledDpiScale 1.5 -ClippingStatus pass -ReadabilityStatus pass`
12. Gold remains blocked until `scripts/verify_windows_installer_visual_audit.py` passes against the promoted installer digest.
13. When `scripts/materialize-public-downloads-bundle.sh` hits this gate, it now refreshes these operator-facing receipts automatically before exiting nonzero:
   - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
   - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json`
   - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
   - `_completion/windows_installer_visual_audit/CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.{txt,generated.json}`
   Use those refreshed receipts as the live recovery surface instead of relying on the raw shell stderr alone.
14. If `WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json` says `windows installer operator ask delivery is stale`, resend the current ask with the published `operator_ask_resend_command` before waiting for more proof. That means the current request text changed after the last Telegram delivery.
15. Long-running auto-import watches started with `--refresh-intake-request` rematerialize the request between polls and rebind discovery roots plus the promoted installer digest. A candidate that matched an older request remains rejected after the shelf changes; the waiting receipt moves to the new version/digest instead of staying pinned to the launch-time request.

Google OAuth linking operator proof:
1. This proof is a browser-backed account-linking gate only. It must not publish downloads or promote a release.
2. Refresh the request receipt and recovery pack before asking the operator to capture evidence:
`cd chummer.run-services && python3 scripts/materialize_google_oauth_linking_operator_evidence_request.py --base-url https://chummer.run && python3 scripts/verify_google_oauth_linking_operator_evidence_request.py`
3. Use the current operator ask text at `chummer.run-services/_completion/google_oauth_linking/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt`.
   - If `GOOGLE_OAUTH_LINKING_PROOF.generated.json` or `OPERATOR_RELEASE_DASHBOARD.generated.json` says `operator ask delivery is stale`, resend the current ask with the published `operator_ask_resend_command` before waiting for more evidence. That means the request text changed after an older Telegram delivery.
4. The required finished receipt path is `chummer.run-services/.codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json`.
5. The operator proof must confirm these steps against an existing Chummer account: `google_sign_in_completed_to_signed_in_state`, `existing_account_linked_google`, `google_sign_in_returned_to_existing_account`, and `linked_provider_visible_on_signed_in_surface`.
   - Current live surfaces: `/home` should stay signed in and keep the Google return path readable, `/account/settings` should keep the primary sign-in and linked sign-in/channel summary readable, and any deeper signed-in account surface that explicitly shows the Google link state can be used for the provider-visible screenshot.
6. Capture at least two screenshots. The current request receipt recommends:
`/docker/chummercomplete/chummer.run-services/.state/google_oauth_linking_operator_evidence/google-signed-in-state.png`
`/docker/chummercomplete/chummer.run-services/.state/google_oauth_linking_operator_evidence/google-provider-linked.png`
`/docker/chummercomplete/chummer.run-services/.state/google_oauth_linking_operator_evidence/google-sign-in-return.png`
7. Drop the exported bundle into the ignored intake folder `.state/incoming_google_oauth_linking_operator_evidence/`, preferably named `google-oauth-linking-operator-evidence-<release-version>.zip`.
8. Discover or watch for the artifact with the intake helpers from this repository root:
`python3 ~/.codex/skills/ea-artifact-intake/scripts/artifact_intake.py discover --pattern "*google-oauth-linking-operator-evidence*.zip" --root "/docker/chummercomplete/chummer.run-services/.state/incoming_google_oauth_linking_operator_evidence" --root "/home/tibor/Downloads" --root "/home/tibor/pCloud Drive/EA"`
`cd chummer.run-services && python3 scripts/auto_import_google_oauth_linking_operator_evidence.py --intake-request .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json --wait-seconds 900 --poll-seconds 10 --refresh-intake-request`
   - `python3 scripts/final_gold_janitor.py` now invokes the same Google auto-import lane with `--wait-seconds 0`, so a bundle that is already sitting in `.state/incoming_google_oauth_linking_operator_evidence/` is picked up on the next gold pass instead of failing behind a generic materializer error.
9. Manual import path from this repository root:
`cd chummer.run-services && python3 scripts/import_google_oauth_linking_operator_evidence_artifact.py /docker/chummercomplete/chummer.run-services/.state/incoming_google_oauth_linking_operator_evidence/google-oauth-linking-operator-evidence-run-20260704-170602.zip --intake-request .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json --verify`
   - That `--verify` import reruns the full intake-request post-import gate chain; it does not stop after the first verifier.
10. Gold remains blocked until `cd chummer.run-services && python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run && python3 scripts/verify_google_oauth_linking_proof.py --require-pass` passes.

Manifest-driven public route proof:
1. `python3 scripts/verify_public_routes_from_manifest.py --base-url https://chummer.run --manifest .codex-design/product/PUBLIC_LANDING_MANIFEST.yaml --output .codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
   - The canonical `https://chummer.run` lane now auto-clamps to a calmer worker budget and a `12s` timeout floor so Black Ledger and other heavier public routes do not false-fail under proof fan-out immediately after publish. Override `CHUMMER_PUBLIC_ROUTE_PROOF_CANONICAL_MAX_WORKERS` or `CHUMMER_PUBLIC_ROUTE_PROOF_CANONICAL_REQUEST_TIMEOUT_SECONDS` only when you intentionally want a stricter stress lane.
2. Local reverse-proxy variant: `python3 scripts/verify_public_routes_from_manifest.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --manifest .codex-design/product/PUBLIC_LANDING_MANIFEST.yaml --output .codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
   - The local verifier now auto-clamps to a serial worker lane and a `12s` per-request timeout floor so a freshly rebuilt public edge does not false-fail on cold docs routes. Override `CHUMMER_PUBLIC_ROUTE_PROOF_LOCAL_MAX_WORKERS` or `CHUMMER_PUBLIC_ROUTE_PROOF_LOCAL_REQUEST_TIMEOUT_SECONDS` only when you intentionally want a stricter stress lane.
3. The verifier checks public routes directly, checks anonymous fallbacks for registered routes without following the redirect, and emits a machine-readable JSON proof packet for publish or audit closeout.

Downloads version marker proof:
1. Source-only proof before deploy: `python3 scripts/verify_downloads_version_marker.py --output /tmp/chummer-downloads-version-source.json`
2. Source/build-lane preflight before an intentional overlay replacement: `python3 scripts/check_public_edge_deploy_preflight.py --skip-overlay-marker-check --output /tmp/chummer-public-edge-source-preflight.json`
3. Local overlay publish-and-activate proof before recreate: `python3 scripts/publish_public_edge_portal_overlay.py --activate --release-channel-receipt "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT" --release-channel-receipt-sha256 "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256" --output /tmp/chummer-public-edge-overlay-publish.json`
   - Require `landingMarkerStatus=pass`, `landingHasTurnAnchor=true`, `landingHasTurnAnchorRedirect=true`, `landingBrowserRedirectStatus=pass`, `landingBrowserRedirectPathMatches=true`, and `landingBrowserRedirectHashMatches=true` in the overlay publish receipt before recreating `chummer-portal`.
   - If a prior publish already populated `.state/public-edge-portal-overlay-next/app`, add `--reuse-staging` so the proof can finish from the staged payload instead of rebuilding.
   - After activation, rerun `python3 scripts/check_public_edge_deploy_preflight.py --output /tmp/chummer-public-edge-overlay-preflight.json` and require `overlayBuildInfoSourceFingerprint.aggregateMatchesCurrentSource=true` before treating the mounted overlay as current or recreating the portal.
4. Local public-edge proof after overlay activation and portal recreate: `python3 scripts/verify_downloads_version_marker.py --base-url http://127.0.0.1:8091 --output /tmp/chummer-downloads-version-local.json`
5. Canonical proof after publish/tunnel refresh: `python3 scripts/verify_downloads_version_marker.py --base-url https://chummer.run --output /tmp/chummer-downloads-version-canonical.json`
   - The public-edge origin surface is the `chummer-portal` service on `http://chummer-portal:8080` from inside the compose network, or `http://127.0.0.1:8091` from the host. Keep the Cloudflare sidecar on `public-origin` so the service-name target stays reachable.
6. Combined local postdeploy gate after overlay activation and recreate: `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url http://127.0.0.1:8091 --output /tmp/chummer-public-edge-postdeploy-local.json`
7. Combined canonical postdeploy gate after publish/tunnel refresh: `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --skip-preflight --expected-build-info "$expected_build_info" --expected-full-deployment-digest-sha256 "$expected_full_deployment_digest_sha256" --expected-pwa-asset-inventory-sha256 "$expected_pwa_asset_inventory_sha256" --output /tmp/chummer-public-edge-postdeploy-canonical.json`
8. Browser-backed local postdeploy gate after overlay activation and recreate: `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url http://127.0.0.1:8091 --require-downloads-status-playwright --playwright-artifact-dir /tmp/chummer-downloads-status-local-browser --output /tmp/chummer-public-edge-postdeploy-local-browser.json`
9. Browser-backed canonical postdeploy gate after publish/tunnel refresh: `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --skip-preflight --expected-build-info "$expected_build_info" --expected-full-deployment-digest-sha256 "$expected_full_deployment_digest_sha256" --expected-pwa-asset-inventory-sha256 "$expected_pwa_asset_inventory_sha256" --require-downloads-status-playwright --playwright-artifact-dir /tmp/chummer-downloads-status-canonical-browser --output /tmp/chummer-public-edge-postdeploy-canonical-browser.json`
10. Browser-backed local postdeploy gate with core PWA viewport proof: `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url http://127.0.0.1:8091 --require-mobile-pwa-viewport-playwright --mobile-pwa-viewport-artifact-dir /tmp/chummer-mobile-pwa-viewport-local-browser --output /tmp/chummer-public-edge-postdeploy-local-pwa-viewport.json`
11. Browser-backed canonical postdeploy gate with core PWA viewport proof: `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --skip-preflight --expected-build-info "$expected_build_info" --expected-full-deployment-digest-sha256 "$expected_full_deployment_digest_sha256" --expected-pwa-asset-inventory-sha256 "$expected_pwa_asset_inventory_sha256" --require-mobile-pwa-viewport-playwright --mobile-pwa-viewport-artifact-dir /tmp/chummer-mobile-pwa-viewport-canonical-browser --output /tmp/chummer-public-edge-postdeploy-canonical-pwa-viewport.json`
12. Browser-backed local postdeploy gate with front-door navigation proof: `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url http://127.0.0.1:8091 --require-frontdoor-navigation-playwright --frontdoor-navigation-artifact-dir /tmp/chummer-frontdoor-navigation-local-browser --output /tmp/chummer-public-edge-postdeploy-local-frontdoor-navigation.json`
13. Browser-backed canonical postdeploy gate with front-door navigation proof: `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --skip-preflight --expected-build-info "$expected_build_info" --expected-full-deployment-digest-sha256 "$expected_full_deployment_digest_sha256" --expected-pwa-asset-inventory-sha256 "$expected_pwa_asset_inventory_sha256" --require-frontdoor-navigation-playwright --frontdoor-navigation-artifact-dir /tmp/chummer-frontdoor-navigation-canonical-browser --output /tmp/chummer-public-edge-postdeploy-canonical-frontdoor-navigation.json`
14. Full browser-backed local postdeploy gate used by release consumers: `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url http://127.0.0.1:8091 --require-downloads-status-playwright --require-mobile-pwa-viewport-playwright --require-frontdoor-navigation-playwright --playwright-artifact-dir /tmp/chummer-downloads-status-local-browser --mobile-pwa-viewport-artifact-dir /tmp/chummer-mobile-pwa-viewport-local-browser --frontdoor-navigation-artifact-dir /tmp/chummer-frontdoor-navigation-local-browser --output /tmp/chummer-public-edge-postdeploy-local-full-browser.json`
15. Full browser-backed canonical postdeploy gate used by release consumers: `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --skip-preflight --expected-build-info "$expected_build_info" --expected-full-deployment-digest-sha256 "$expected_full_deployment_digest_sha256" --expected-pwa-asset-inventory-sha256 "$expected_pwa_asset_inventory_sha256" --require-downloads-status-playwright --require-mobile-pwa-viewport-playwright --require-frontdoor-navigation-playwright --playwright-artifact-dir /tmp/chummer-downloads-status-canonical-browser --mobile-pwa-viewport-artifact-dir /tmp/chummer-mobile-pwa-viewport-canonical-browser --frontdoor-navigation-artifact-dir /tmp/chummer-frontdoor-navigation-canonical-browser --output /tmp/chummer-public-edge-postdeploy-canonical-full-browser.json`
16. The combined local postdeploy proof must report `preflightStatus=pass` and `preflightBlockingLockCount=0`; any nonzero blocking-lock count means the deploy lane is still gated. `preflightActiveLockCount` may be nonzero only when stale foreign build lanes are the remaining entries and the receipt exposes them through `preflightAutoIgnoredStaleForeignLockCount` or `preflightStaleForeignLocksIgnored=true`.
    - Release consumers now also require the flattened top-level postdeploy fields `preflightOverlayRoot`, `preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource`, `preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256`, `preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256`, `preflightOverlayBuildInfoSourceFingerprintMissingKeys`, `preflightOverlayBuildInfoSourceFingerprintMismatchedKeys`, `expectedFullDeploymentDigestSha256`, `pwaFullDeploymentDigestSha256`, and `pwaFullDeploymentDigestMatchesExpected`. Missing any of them, or a digest mismatch, is a stale/wrong-deployment failure even if the receipt status says `pass`.
17. Do not use `--skip-preflight` for local public-edge deploy proof. It is reserved for post-fact canonical `https://chummer.run` checks where local build locks cannot describe the already published edge.
18. The combined local and canonical postdeploy proof must report `participateIframeShellStatus=pass`; any failure means `/participate` or `/partizipate` is still serving the removed wrapper copy instead of the iframe-only shell.
19. The live proof must report `downloads_marker=true`, `status_redirect_marker=true`, and concrete `downloads_version_text` / `status_redirect_version_text` values.
20. Release-ready, final-gold, and dashboard materializers use the full browser-backed postdeploy receipt; do not publish a current launch proof from the narrower single-proof commands above.
21. Release consumers must reject stale `PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json` receipts even when `status=pass` if they are missing required current fields: `preflightStatus`, `preflightBlockingLockCount`, `preflightStaleForeignLockCount`, `preflightStaleForeignLocksIgnored`, `expectedFullDeploymentDigestSha256`, `pwaFullDeploymentDigestSha256`, `pwaFullDeploymentDigestMatchesExpected`, `downloadsStatus`, `downloadsHasMarker`, `statusRedirectHasMarker`, `statusRedirectHeading`, `statusRedirectHeadingRecognized`, `statusRedirectHeadingExpected`, `statusRedirectHeadingMatchesReleaseChannel`, `statusRedirectHeadingUsesGenericUpdatedCopy`, `pwaStaticStatus`, `mobileLedgerStatus`, `readyMobileHandoffStatus`, `downloadsStatusBrowserStatus`, `mobilePwaViewportStatus`, `mobilePwaViewportRouteCount`, `mobilePwaViewportViewportCount`, `participateIframeShellStatus`, `participateIframeRouteCount`, `frontdoorNavigationStatus`, `frontdoorNavigationGatedTargets`, `frontdoorNavigationLedgerPrimary`, `frontdoorNavigationAnchorArtifactContract`, `frontdoorNavigationAnchorEntryUrl`, `frontdoorNavigationAnchorFinalUrl`, `frontdoorNavigationAnchorFinalPath`, `frontdoorNavigationAnchorFinalHash`, `frontdoorNavigationAnchorPwaManifestPath`, `frontdoorNavigationAnchorPwaRole`, `frontdoorNavigationAnchorBlazorShell`, `frontdoorNavigationAnchorSessionIdPresent`, `frontdoorNavigationAnchorDeviceIdPresent`, and `frontdoorNavigationAnchorFailure`.
22. Dashboard and final-gold receipts must surface `missing postdeploy fields` instead of silently treating an old schema as current proof.
23. A source-only pass is not deployment proof. Do not close the downloads marker or Participate shell gate until the preflight passes and the local and canonical live proofs pass after the public-edge image has been rebuilt.
24. Migrate the immutable shelf in two phases, with both migration flags explicitly set in the operator environment. For the controlled first activation only, deploy readers with `CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED=false` and `CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED=true`, then perform exactly one governed initialized activation; do not blindly retry an unknown activation outcome. Verify a valid `current.json`, `.release-shelf-layout-v1`, and the matching committed activation receipt. `current.json` is the commit point and remains readable if the post-commit marker write is interrupted. After all three objects are verified, permanently set `CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED=true` and `CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED=false` on every production reader, redeploy, and require `/api/ready/publication` to pass before serving downloads. This is the durable downgrade sentinel: deleting both marker and pointer must then fail closed rather than resume serving mutable top-level files. Never reopen the one-time migration flag or set the layout-required flag back to `false` to recover traffic. `bash scripts/runbook.sh release-shelf-cutover-help` prints this sequence without mutating the shelf.
25. A production local-filesystem shelf is single-writer. The API promotion service durably creates `.release-shelf-writer-policy.json` with mode `server-journal-v1`; after that marker exists, use only the staged HTTP upload-session API. `runbook.sh`, the Python generation helper, fixed-path/nightly publishers, source materializers, and cross-repository mirrors must refuse that root. Do not delete or bypass the policy to recover a release. Reconcile `.release-shelf-activation-intent.json` and its immutable per-receipt history first; object-storage/S3 publication uses a separate protocol and is not a substitute for the local server journal.

Flagship public-edge proof pack:
1. Local pack after overlay activation/recreate:
`bash scripts/ai/run_flagship_public_edge_verification.sh --base-url http://127.0.0.1:8091 --output-dir /tmp/chummer-flagship-public-edge-local`
2. Canonical pack after publish/tunnel refresh:
`bash scripts/ai/run_flagship_public_edge_verification.sh --base-url https://chummer.run --output-dir /tmp/chummer-flagship-public-edge-canonical --skip-preflight`
3. The helper bundles the current flagship public-edge proof slice into one rerunnable command: horizons route/manifest coverage, public PWA static assets, mobile ledger opt-in boundary, ready mobile handoff contract, Participate iframe shell, live surface parity, and the full browser-backed postdeploy gate with downloads/mobile/offline/front-door proofs.
4. The output directory keeps the generated receipts together with the Playwright artifact folders under `public-edge-browser-proofs/`.

PWA/static asset proof:
1. Source-only proof before deploy: `python3 scripts/verify_public_pwa_static_assets.py --output /tmp/chummer-pwa-static-assets-source.json`
2. Canonical non-mutating proof: `python3 scripts/verify_public_pwa_static_assets.py --base-url https://chummer.run --expected-full-deployment-digest-sha256 "$expected_full_deployment_digest_sha256" --expected-asset-inventory-sha256 "$expected_pwa_asset_inventory_sha256" --output /tmp/chummer-pwa-static-assets-canonical.json`
3. Local public-edge proof after a rebuild: `python3 scripts/verify_public_pwa_static_assets.py --base-url http://127.0.0.1:8091 --expected-full-deployment-digest-sha256 "$expected_full_deployment_digest_sha256" --expected-asset-inventory-sha256 "$expected_pwa_asset_inventory_sha256" --output /tmp/chummer-pwa-static-assets-local.json`

`expected_pwa_asset_inventory_sha256` must come from `publicPwaStaticProof.assetDigestInventory.sha256` in a sealed preflight receipt. When `--skip-preflight` is used, that digest is an external trust root: transfer it independently from the preflight lane and do not derive it from the mutable live checkout. The standard flagship helper does not skip preflight; an explicit skip fails closed unless this anchor is supplied.
4. The verifier checks all public web manifests, the service worker, mobile/play static assets, PWA screenshots/icons, `/ready/handoff/mobile.json`, and the personalized `/mobile/pwa/ledger.json` privacy boundary.
5. Source-only proof reports `mode=source` and checks route attributes plus `wwwroot` files only. It is not deployment proof.
6. The ledger stream must be listed in `NON_CACHEABLE_PATHS` and must not appear in `PRECACHE_URLS`; a pass packet reports `ledger_stream_non_cacheable=true` and `ledger_stream_precached=false`.
7. Keep these proof files in `/tmp` during coordination or audit-only runs. Copy them into `.codex-studio/published/` only inside an owned release or publish lane.

Mobile PWA ledger boundary proof:
1. Source-only proof: `python3 scripts/verify_mobile_pwa_ledger_boundary.py --output /tmp/chummer-mobile-pwa-ledger-boundary-source.json`
2. Local public-edge proof: `python3 scripts/verify_mobile_pwa_ledger_boundary.py --base-url http://127.0.0.1:8091 --output /tmp/chummer-mobile-pwa-ledger-boundary-local.json`
3. Canonical proof: `python3 scripts/verify_mobile_pwa_ledger_boundary.py --base-url https://chummer.run --output /tmp/chummer-mobile-pwa-ledger-boundary-canonical.json`
4. The live proof must report `payload_status` in `opt_in_required`, `no_world_data`, `live`, or `world_not_followed`.
5. The live proof must report `cache_control` containing `private, no-store` and `vary` containing both `Cookie` and `Authorization`.
6. If the live payload is `world_not_followed`, the proof must reject live turn cadence leaks such as `world_turn`, `continuity`, `hot_district`, `move_district`, `turn_route`, and `newsreel_route`.

Ready mobile handoff proof:
1. Source-only proof: `python3 scripts/verify_ready_mobile_handoff_contract.py --output /tmp/chummer-ready-mobile-handoff-source.json`
2. Local public-edge proof: `python3 scripts/verify_ready_mobile_handoff_contract.py --base-url http://127.0.0.1:8091 --output /tmp/chummer-ready-mobile-handoff-local.json`
3. Canonical proof: `python3 scripts/verify_ready_mobile_handoff_contract.py --base-url https://chummer.run --output /tmp/chummer-ready-mobile-handoff-canonical.json`
4. The live proof must report `tool_ids` containing `inventory`, `health`, `ammo`, `modifiers`, `quick_rolls`, and `living_world`.
5. The live proof must report packet roles `player`, `gm`, and `organizer`, plus `pwa_route=/mobile`, `continuity_route=/play/continuity`, and `frontdoor_launch_route=/mobile/player`.
6. The live proof must report `role_routes` for `Player` and `GameMaster`, including `/mobile/player`, `/mobile/gm`, `/manifest.player.webmanifest`, `/manifest.gm.webmanifest`, and the matching manifest start URLs.
7. The proof must reject handoffs that omit the playtime boundary, account opt-in, followed-world selection, GM-authority wording, the default player launch route, or the role-specific PWA manifest routes.

Participate iframe shell proof:
1. Source-only proof: `python3 scripts/verify_participate_iframe_shell.py --output /tmp/chummer-participate-iframe-shell-source.json`
2. Local public-edge proof: `python3 scripts/verify_participate_iframe_shell.py --base-url http://127.0.0.1:8091 --output /tmp/chummer-participate-iframe-shell-local.json`
3. Canonical proof: `python3 scripts/verify_participate_iframe_shell.py --base-url https://chummer.run --output /tmp/chummer-participate-iframe-shell-canonical.json`
4. The source proof must report the existing `data-chummer-participate-frame` iframe and `participate-board-fallback` paths, plus minimal `Summary: "Participate"` builders for both Participate shell builders.
5. The live proof must report `route_count=2` for `/participate` and `/partizipate`, with `iframe_route_count` or `offline_fallback_route_count` covering both routes.
6. The live proof must reject the removed visible wrapper copy: `Public requests, clear bugs, useful ideas.`, `<p class="eyebrow">Board</p>`, and `participate-hosted__header`.

Mobile PWA viewport proof:
1. Local browser proof: `BASE_URL=http://127.0.0.1:8091 CHUMMER_COMPLETION_DIR=/tmp/chummer-mobile-pwa-viewport-local-browser npx playwright test tests/public/mobile-pwa-viewport-smoke.spec.ts --workers=1 --reporter=line`
2. Canonical browser proof: `BASE_URL=https://chummer.run CHUMMER_COMPLETION_DIR=/tmp/chummer-mobile-pwa-viewport-canonical-browser npx playwright test tests/public/mobile-pwa-viewport-smoke.spec.ts --workers=1 --reporter=line`
3. The artifact `MOBILE_PWA_VIEWPORT_SMOKE.generated.json` must report `route_count=3`, `viewport_count=3`, and no horizontal overflow for `/mobile`, `/play`, and `/play/continuity` across `phone-390`, `tablet`, and `desktop-1366`.

Front-door navigation proof:
1. Local browser proof: `BASE_URL=http://127.0.0.1:8091 CHUMMER_COMPLETION_DIR=/tmp/chummer-frontdoor-navigation-local-browser npx playwright test tests/public/frontdoor-mobile-launch.spec.ts tests/public/black-ledger-frontdoor.spec.ts --workers=1 --reporter=line`
2. Canonical browser proof: `BASE_URL=https://chummer.run CHUMMER_COMPLETION_DIR=/tmp/chummer-frontdoor-navigation-canonical-browser npx playwright test tests/public/frontdoor-mobile-launch.spec.ts tests/public/black-ledger-frontdoor.spec.ts --workers=1 --reporter=line`
3. The artifacts `FRONTDOOR_MOBILE_LAUNCH.generated.json` and `BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json` must report Build and Play as gated signed-out targets, homepage horizontal overflow under 1px, and `ledger_primary=false`.

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
5. When the bundle ships `proof/windows`, the deployed shelf exposes both the proof dispatch routes and the direct proof files.

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
