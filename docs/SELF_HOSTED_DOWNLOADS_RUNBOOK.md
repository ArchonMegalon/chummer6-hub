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

## Recommended Production Topology

1. Default recommendation: use `CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR` with a self-hosted runner that can write directly into the portal downloads storage mount.
2. Reason: this keeps `/downloads/` self-hosted, lets the deploy job verify both the local manifest file and the live portal manifest, and matches the canonical topology enforced in repo docs.
3. Treat object storage as the alternate topology for environments where the runner cannot write to portal storage directly; keep portal proxying and live manifest verification enabled there too.
4. Start from [`docs/examples/self-hosted-downloads.env.example`](examples/self-hosted-downloads.env.example) and adapt it to your portal base URL and storage target.

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
   - Do not use raw `docker compose ... up -d --build chummer-portal` for release publication. The guarded wrapper source-gates the audited checkout, builds `chummer-run-api:local` from explicit contexts, recreates `chummer-portal` with `--no-build`, and postdeploy-gates the exact image id before the deploy is considered publishable.
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
The restore command validates the approved image id, records Docker created time, tags, digests, and labels for any drifted image it replaces, repoints the configured mutable tag plus explicitly matched local aliases, recreates only `chummer-portal` with `docker compose up -d --no-build --no-deps --force-recreate`, repairs bounded image drift during the optional stability window, and retries the runtime image guard plus the downloads/status, mobile viewport, and Open Chummer navigation browser proofs in its postdeploy receipt while the container warms up.

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
