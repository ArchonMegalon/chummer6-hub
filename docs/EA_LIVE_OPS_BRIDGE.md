# EA Live Ops Bridge

This repo does not reimplement the private EA runtime control plane. It exposes a local bridge to the existing EA live-ops entrypoint at `/docker/EA/scripts/ea_live_ops.py` so run-services can:

- probe live operator readiness
- inspect Telegram and WhatsApp delivery posture
- capture secret-safe readiness receipts
- point operators at the exact next action instead of ad hoc terminal commands

## Local bridge

Use the bridge from this repo root:

```bash
python3 scripts/ea_live_ops.py probe-operator-readiness
python3 scripts/ea_live_ops.py probe-whatsapp-readiness
python3 scripts/ea_live_ops.py probe-telegram-readiness
```

The bridge forwards directly into the EA runtime script and preserves its exit code.

If the EA runtime is mounted somewhere other than `/docker/EA/scripts/ea_live_ops.py`, set:

```bash
EA_LIVE_OPS_SCRIPT_PATH=/custom/path/to/ea_live_ops.py
```

before running the bridge or the receipt materializers.

## Receipt flow

Materialize a local operator-readiness receipt:

```bash
python3 scripts/materialize_ea_operator_readiness.py
python3 scripts/verify_ea_operator_readiness.py
```

Default output:

- `.codex-studio/published/EA_OPERATOR_READINESS.generated.json`

Materialize the My Media public-surface receipt:

```bash
python3 scripts/materialize_mymedia_public_surface.py
python3 scripts/verify_mymedia_public_surface.py
python3 scripts/verify_mymedia_public_surface.py --require-pass
```

Default output:

- `.codex-studio/published/MYMEDIA_PUBLIC_SURFACE.generated.json`

Materialize the host workload runtime-health receipt:

```bash
python3 scripts/materialize_host_workload_runtime_health.py
python3 scripts/verify_host_workload_runtime_health.py
```

Default output:

- `.codex-studio/published/HOST_WORKLOAD_RUNTIME_HEALTH.generated.json`

Important-work Teable sync stays bounded during release/control-plane refreshes:

```bash
python3 scripts/sync_important_work_to_teable.py --sync
```

The sync uses the shared Teable request timeout budget from:

- `CHUMMER_TEABLE_HTTP_TIMEOUT_SECONDS`

and now has its own per-run deadline:

- `CHUMMER_TEABLE_IMPORTANT_WORK_SYNC_DEADLINE_SECONDS`

If Teable is slow or degraded, the script should write a failed `TEABLE_IMPORTANT_WORK.generated.json` receipt with a deadline/timeout error instead of holding `materialize_release_ready_receipt.py`, `materialize_operator_release_dashboard.py`, or `final_gold_janitor.py` open indefinitely.

Host workload guardrails for Plex/cloud playback are mirrored in-repo as well:

```bash
python3 scripts/verify_host_workload_guardrails.py --repo-only
python3 scripts/verify_host_workload_guardrails.py
python3 scripts/sync_host_workload_guardrails.py
```

Use the live verifier when Plex reports `The transcoder process crashed` but the deeper cause may be a stale cloud-mount namespace rather than an ffmpeg fault. The verifier checks:

- repo-managed watchdog/mount assets are present and match expected recovery snippets
- live host assets match the repo mirror
- watchdog timers are active on the host
- the Plex container can still byte-read both the pCloud and Internxt probe files
- qBittorrent can still write to its configured save path when the container is running
- legacy Plex alias paths under `/docker/plex/media/*` are still wired

Use the runtime-health receipt when the fail-closed verifier is correctly reporting a degraded live state but the operator needs the sharper answer about what kind of degradation is present. The runtime-health receipt translates the same lane into:

- `runtime_status=ready|degraded|blocked`
- explicit `blocking_findings` and `advisory_findings`
- whether Plex namespace repair was deferred because active sessions were present
- whether qBittorrent resumed live writes but still has fast-resume mismatches from earlier storage drift
- the current pCloud rclone cache mode and cache usage

Materialize the qBittorrent staging-hygiene receipt when the operator needs the sharper answer about old orphan `.partial` files, dead metadata grabs, or stale stalled downloads that are no longer a mount outage but still keep filling the staging volume. The receipt resolves qBittorrent's live container save path back to the host staging bind before it scans the filesystem, so it stays honest even when qB downloads to `/downloads` inside the container:

```bash
python3 scripts/materialize_qbittorrent_staging_hygiene.py
python3 scripts/verify_qbittorrent_staging_hygiene.py
python3 scripts/materialize_qbittorrent_staging_hygiene.py --apply-prune-orphan-partials
python3 scripts/materialize_qbittorrent_staging_hygiene.py --apply-enable-queueing
python3 scripts/materialize_qbittorrent_staging_hygiene.py --apply-requeue-dead-stalled-downloads
```

That receipt publishes:

- `runtime_status=ready|degraded|blocked`
- orphan `.partial` file counts and GiB after ignoring files still referenced by live qBittorrent torrents
- old `metaDL` / `forcedMetaDL` candidates that no longer have swarm evidence
- old `stalledDL` candidates plus long-inactive zero-speed `downloading` items that should be requeued or deleted instead of silently sitting in Sonarr
- old `checkingDL` / `checkingResumeData` candidates that have stayed stuck past the recovery threshold
- applyable `--apply-requeue-dead-stalled-downloads` lane for stale `stalledDL` items that should be paused then resumed
- whether qBittorrent queueing is disabled even though active-download limits are configured
- whether the current active download count is still above the runtime limit

Use `--apply-prune-orphan-partials` only when the receipt has already shown old orphan partials and the operator wants the guarded cleanup path that deletes only files older than the configured threshold and no longer referenced by any live qBittorrent torrent.
Use `--apply-enable-queueing` when the receipt shows `qbittorrent_queueing_disabled`. That path re-applies the queueing/runtime guardrails through the qBittorrent WebUI API so the limits persist in qB itself instead of living only in operator memory.
Use `--apply-requeue-dead-stalled-downloads` when the receipt shows `qbittorrent_dead_stalled_downloads_present` and those torrents have stayed stalled past `min_dead_stalled_age_minutes`. This lane does a guarded pause/resume cycle on each stale stalled hash and reports both `dead_stalled_hashes_requeued` and `dead_stalled_requeue_errors` in the observation.
The host watchdog service reads `/etc/default/qbittorrent-staging-hygiene-watchdog`, which now carries the reusable recovery thresholds and enables queueing re-application by default without baking those operator choices into the service unit.

The same repo-managed host-workload lane now also carries the additive Plex-to-Internxt mirror service:

- `plex-internxt-mirror.service`
- `plex-internxt-mirror.timer`

That service mirrors `Movies` and `TV` from pCloud into Internxt while preserving the existing Internxt bucket layout for `Movies` and `TV`.
Requested intake is routed into those same destination trees instead of maintaining a separate Internxt `Requested` mirror:

- `Requested/Movies` -> `PLEX/Movies/<bucket>/<title>`
- `Requested/TV` -> `PLEX/TV/<bucket>/<show>`
- `Requested/Unsorted` and `Requested/_inbox` -> classified into Movies or TV before copy

The copy path uses `rsync --inplace` for the bucketed `Movies`, `TV`, and requested-routing writes because the Internxt mount can reject rsync's default temp-file rename flow with `Input/output error (5)`.
The installed host mirror now also writes `/run/plex-internxt-mirror/status.json` atomically on each phase/progress update and on failure/complete exit. `materialize_host_workload_runtime_health.py` consumes that machine-readable state first and only falls back to recent `plex-internxt-mirror.service` journal progress when an older in-flight run predates the status file contract.

## Status semantics

These EA-adjacent receipts now separate structural verification from semantic live state.

- `status`
  - structural contract result only
  - `pass` means the probe ran, the receipt shape is coherent, and no secret-bearing fields leaked into the published artifact
- `structural_status`
  - explicit copy of the structural contract result so downstream consumers do not have to infer that `status` is structural
- `effective_status`
  - semantic runtime state for the primary surface represented by the receipt
  - `EA_OPERATOR_READINESS.generated.json` uses `operator_status`
  - `MYMEDIA_PUBLIC_SURFACE.generated.json` uses `public_surface_status`

Use the semantic fields for operator UX and dashboards:

- EA operator readiness
  - `operator_status`
  - `operator_ready`
  - `attention_component_keys`
  - `blocked_component_keys`
  - `next_action_component_keys` for blocking or degraded follow-ups
  - `advisory_action_component_keys` for ready-but-still-actionable follow-ups such as console checks or approval capture
- My Media public surface
  - `public_surface_status`
  - `public_surface_ready`
  - `mymedia_status`

Published `stdout_tail` and `stderr_tail` fields are operator-safe summaries, not raw probe dumps. If deeper runtime diagnostics are needed, rerun the bridge command directly instead of treating the published receipt as a log sink.

Published `source` and `source_runtime` fields use logical IDs such as `script:ea_live_ops.py` and `ea_live_ops.bridge`, not absolute host filesystem paths.
Published component `source` markers and any probe-summary `source=` tokens are sanitized the same way; local script paths collapse to logical `script:<name>` markers, and loopback URLs collapse to `host-local:///...` locators.
Published loopback `next_action_href` values are normalized to `host-local:///...` locators, and volatile session identifiers inside those host-local locators are redacted. Public HTTPS URLs remain unchanged.
Published operator recovery command lists should not leak loopback base URLs either. If a recovery step needs to mention a base URL in a published receipt, prefer the public HTTPS base or a host-local locator instead of `http://127.0.0.1...`.

Do not treat a structural `status=pass` receipt as proof that no operator action remains. For example:

- EA can be structurally `pass` while `effective_status=ready_with_actions`
- My Media can be structurally `pass` while `mymedia_status=ready_library_scan_in_progress`

Google OAuth linking proof and operator recovery pack:

```bash
python3 scripts/materialize_google_oauth_linking_operator_evidence_request.py
python3 scripts/verify_google_oauth_linking_operator_evidence_request.py
python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run
```

When the live proof is still blocked on missing browser-backed operator evidence, the proof receipt should still verify that the recovery pack is coherent:

- request receipt exists and targets the current required evidence path
- ask text and ask metadata agree on paths, receipt name, and message digest
- evidence template matches the required steps and minimum screenshot count
- proof failure should then narrow to the real missing operator evidence, not a broken recovery pack
- if the current ask text no longer matches the already-sent Telegram delivery, the proof and dashboard should surface `operator ask delivery is stale` plus the resend command before anyone waits on the old message

When valid operator evidence already exists at the required path, the request receipt should suppress itself to `not_required` instead of continuing to advertise a stale operator ask.

## Current recovery model

- `telegram`
  - expected to be ready when the EA local binding scan passes
- `whatsapp`
  - readiness is blocked until the WhatsApp Web sidecar is paired again, but the aggregate receipt should count the QR recovery lane once
- `whatsapp_pairing`
  - points at the current sidecar pairing surface and QR state
- `google_workspace_oauth`
  - may be structurally healthy while still requiring an operator retry/account-selection handoff
- `pushbullet`
  - remains optional operator delivery; missing tokens should show as setup-required, not as a secret leak or a hard blocked-count increment
- `mymedia_alexa`
  - `ready_library_scan_in_progress` is a stable live state when tracks are already present; it should not inflate blocker counts or operator next-action noise
- `mymedia_public_surface`
  - tracks the Cloudflare-backed public console separately from library indexing so `mymedia.girschele.com` can be green even while a scan is still running

## Boundary

This bridge is runtime/governance-adjacent only. It does not make EA the canonical product truth for Chummer surfaces.
