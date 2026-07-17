# Host Workload Guardrails

This directory is the repo mirror for the local host guardrails that keep Plex usable while EA, builds, and background agents are active.

## Managed assets

- `media-cache-guard.*`
  - Host target: `/usr/local/sbin/media-cache-guard.sh`, `/etc/systemd/system/media-cache-guard.{service,timer}`
  - Keeps rebuildable Docker cache from consuming the rclone VFS reserve required for playback.
- `media-cache-guard.service.d-10-budget.conf`
  - Host target: `/etc/systemd/system/media-cache-guard.service.d/10-budget.conf`
  - Pins the minimum free-space reserve to 20 GiB so the pCloud write cache can still use its full 12 GiB budget without pushing `/` into the danger zone.
- `plex-stream-watchdog.*`
  - Host target: `/usr/local/sbin/plex-stream-watchdog.sh`, `/etc/default/plex-stream-watchdog`, `/etc/systemd/system/plex-stream-watchdog.{service,timer}`
  - Recovery rule: skip Plex container restarts while Plex reports active sessions, and pick the restart up on the next idle recovery pass.
  - Probes pCloud and Internxt on the host and from inside the Plex container, restarting Plex when a container bind mount goes stale.
- `plex-stream-watchdog.timer.d-10-fast-container-check.conf`
  - Host target: `/etc/systemd/system/plex-stream-watchdog.timer.d/10-fast-container-check.conf`
  - Runs the Plex container probe every five minutes instead of waiting for the hourly default.
- `rclone-mount-pcloud-cache-tuning.conf`
  - Host target: `/etc/systemd/system/rclone-mount@pcloud.service.d/20-cache-tuning.conf`
  - pCloud mount profile with a bounded write cache budget that keeps Plex reads out of the same disk cache qBittorrent needs for uploads.
- `rclone-mount-internxt-cache-tuning.conf`
  - Host target: `/etc/systemd/system/rclone-mount@internxt.service.d/zz-cache-budget.conf`
  - Bounded Internxt cache profile with a tighter 4 GiB VFS cap so the mirror lane cannot consume the entire host reserve that pCloud playback still needs.
- `rclone-mount@.service.d-80-media-priority.conf`
  - Host target: `/etc/systemd/system/rclone-mount@.service.d/80-media-priority.conf`
  - Keeps playback mounts at normal service priority while other background jobs are de-prioritized elsewhere.
- `plex-internxt-mirror.*`
  - Host target: `/usr/local/sbin/plex-internxt-mirror.sh`, `/etc/systemd/system/plex-internxt-mirror.{service,timer}`
  - Mirrors `/mnt/pcloud/PLEX/Movies` and `/mnt/pcloud/PLEX/TV` into Internxt.
  - Routes `/mnt/pcloud/PLEX/Requested` into the right destination trees instead of mirroring a separate Requested shelf:
    - `Requested/Movies` -> bucketed `.../PLEX/Movies/<bucket>/<title>`
    - `Requested/TV` -> bucketed `.../PLEX/TV/<bucket>/<show>`
    - `Requested/Unsorted` and `Requested/_inbox` -> classified into Movies or TV by filename/directory heuristics before copy
  - Uses `rsync --inplace` for both Movies and TV copies because the Internxt mount can fail rsync's temp-file rename step with `Input/output error (5)` on artwork sidecars.
  - Publishes machine-readable live progress to `/run/plex-internxt-mirror/status.json` with phase, overall progress, current item, exit code, and last error so EA receipts can compute ETA without scraping raw logs.
  - Runs at `Nice=10` with idle I/O so the long copy lane stays behind interactive playback and foreground work.
- `qbittorrent-storage-watchdog.*`
  - Host target: `/usr/local/sbin/qbittorrent-storage-watchdog.sh`, `/etc/systemd/system/qbittorrent-storage-watchdog.{service,timer}`
  - Watches qBittorrent's own storage log for recent `Socket not connected` write failures, ignores stale errors from before the current container start, and restarts qBittorrent once the configured save path is writable again.
  - If the save path is still unhealthy, it triggers `rclone-mount-watchdog.service` instead of restarting qBittorrent blindly.
- `qbittorrent-staging-hygiene-watchdog.*`
  - Host target: `/usr/local/sbin/qbittorrent-staging-hygiene-watchdog.sh`, `/etc/systemd/system/qbittorrent-staging-hygiene-watchdog.{service,timer}`
  - Runtime defaults: `/etc/default/qbittorrent-staging-hygiene-watchdog`
  - Periodically runs staging-hygiene recovery operations: requeue stalled/meta/checking torrents, clear force-started torrents for queue fairness, and optionally prune dead/stale candidates after recovery.
  - Runs with background priority (`Nice=10`) and uses a lockfile to avoid overlapping recovery passes.
- `rclone-mount-watchdog.*`
  - Host target: `/usr/local/bin/rclone-mount-watchdog.sh`, `/etc/systemd/system/rclone-mount-watchdog.{service,timer}`
  - Recovery rule: require repeated probe failures before detaching a cloud mount, and defer mount restarts while Plex has active sessions.
  - Repairs stale or missing rclone mounts, refreshes `mymediaalexa` after successful cloud-mount recovery, and immediately triggers the Plex probe path.
  - Also detects stale bind-mount namespaces inside long-running containers after the host mount itself has recovered, then restarts only the affected consumers (`plex`, `mymediaalexa`, `sonarr_v2`, `radarr_v2`, `qbittorrent_pia`) instead of bouncing the cloud mount again.
  - Supports per-container probe/destination overrides for consumers that do not mount the host cloud path directly. `mymediaalexa` is checked on `/medialibrary`, so a stale My Media bind namespace can be repaired even while the host `/mnt/pcloud` mount itself stays healthy.
  - Detects runtime/config drift for selected mounts such as Internxt's VFS cache budget. When the live `rclone rc vfs/stats` cache limit no longer matches the installed systemd unit/drop-ins, it defers restarts while blocker units or active Plex sessions exist, then restarts the mount automatically once the lane is idle.

## Recovery notes

- Keep the legacy Plex aliases under `/docker/plex/media/{Movies,TV Shows,Requested}` pointing at the current library roots. Older Plex library entries can still depend on those surfaces.
- The cache guard only prunes rebuildable Docker cache, dangling images, apt cache, and old journal data. It does not delete media files.
- qBittorrent stages active downloads on the host at `/docker/arr-v2/staging/downloads`, mounted into the downloader and Arr containers as `/downloads`. The pCloud mount remains the library/import destination instead of the live torrent write path.
- If Plex reports `The transcoder process crashed` together with `Socket not connected` or `Couldn't find the file to stream`, treat that as a stale cloud-mount namespace until proven otherwise. The first recovery check is whether the host can read the file while the Plex container cannot.
- If My Media reports watch-folder errors but the host can still read `/mnt/pcloud/My Music`, treat that as a stale `mymediaalexa` bind namespace first. The watchdog now probes `/medialibrary` inside the container and restarts only `mymediaalexa` when that namespace goes stale.
- If My Media watch folders have recovered to `serving` and `/medialibrary` is readable again, but the probe still reports `blocked_connection_not_ready`, the mount problem is already fixed. The next recovery lane is the Amazon connection itself, not another watch-folder repair.
- If most qBittorrent torrents are suddenly `stalled` after cloud-mount errors, inspect `/docker/arr-v2/qbittorrent-vpn/qBittorrent/logs/qbittorrent.log` for `File error alert ... Socket not connected`. The qBittorrent storage watchdog should either trigger `rclone-mount-watchdog.service` while the path is still unhealthy or restart `qbittorrent_pia` once the configured qBittorrent save path is writable again.
- When `verify_host_workload_guardrails.py` is fail-closing because the Plex container still has a stale mount namespace, use `materialize_host_workload_runtime_health.py` to distinguish a truly blocked workload from a deferred repair state where qBittorrent writes have recovered but Plex is waiting for active sessions to end before the watchdog restarts it.
- When qBittorrent is writing again but the active staging bind keeps filling with old `.partial` debris or dead metadata grabs, use `materialize_qbittorrent_staging_hygiene.py` plus `verify_qbittorrent_staging_hygiene.py`. That receipt maps qBittorrent's container save path back to the host staging root, ignores files still referenced by live qBittorrent torrents, and highlights only old orphan partials, dead metadata downloads, long checking torrents, and stalled downloads that should be requeued or deleted.
- When the hygiene receipt has already identified old orphan partials, `materialize_qbittorrent_staging_hygiene.py --apply-prune-orphan-partials` is the guarded cleanup path. It only deletes `.partial` files older than the configured threshold and only when they are no longer referenced by any live qBittorrent torrent.
- The same hygiene lane also checks qBittorrent runtime guardrails. If it reports `qbittorrent_queueing_disabled`, run `materialize_qbittorrent_staging_hygiene.py --apply-enable-queueing` so qB persists `queueing_enabled=true` alongside the configured active-download limits.
- If the receipt includes stale `qbittorrent_dead_stalled_downloads_present`, run `materialize_qbittorrent_staging_hygiene.py --apply-requeue-dead-stalled-downloads` before touching trackers or indexer queues. This lane now treats both explicit `stalledDL` items and long-inactive zero-speed `downloading` items as dead-stalled candidates, then pauses/resumes each candidate and reports outcomes in `dead_stalled_hashes_requeued` and `dead_stalled_requeue_errors`.
- If the receipt includes `qbittorrent_dead_metadata_downloads_present`, run `materialize_qbittorrent_staging_hygiene.py --apply-requeue-dead-meta-downloads` to requeue stale metadata grabs in place. If they remain unresolved, add `--apply-delete-dead-meta-downloads` to clear the stuck metadata entries after recovery attempts.
- If the receipt includes `qbittorrent_long_checking_downloads_present`, run `materialize_qbittorrent_staging_hygiene.py --apply-requeue-dead-checking-downloads` before touching trackers or indexer queues. This lane pauses and resumes each old candidate checking torrent and reports outcomes in `dead_checking_hashes_requeued` and `dead_checking_requeue_errors`.
- The installed watchdog now reads `/etc/default/qbittorrent-staging-hygiene-watchdog`, so the recovery thresholds, delete posture, and `QBIT_ENSURE_QUEUEING=1` guardrail can be tuned without editing the service or shell script.
- The Internxt mirror service is additive, not destructive. It updates Internxt to include the current pCloud Movies/TV trees plus requested items routed into the right library roots, but it does not delete extra content that already exists on Internxt.
- `materialize_host_workload_runtime_health.py` now reads the Internxt mirror state file when available and falls back to recent `plex-internxt-mirror.service` journal progress only while a pre-status-file run is still active. That keeps the published EA receipt operator-safe while still surfacing live progress and ETA.
- If that old journal-fallback path is stuck on a very large current directory copy and there is no status file yet, the receipt now suppresses `mirror_eta_seconds` instead of publishing a misleading count-based ETA. In that case it exposes `eta_suppressed_reason=journal_current_entry_long_running` plus the current source/destination byte counts and progress ratio for the active entry.
- Do not hand-edit the installed host copies without backporting the same change here first.

## Verification

Run the reusable verifier from the repo root:

```bash
python3 scripts/verify_host_workload_guardrails.py
```

Use `--repo-only` when you only want to validate the mirrored assets and not the live host.

## Sync

Preview what would be installed onto a host root:

```bash
python3 scripts/sync_host_workload_guardrails.py
```

Apply the mirrored guardrails into an alternate root for staging/tests:

```bash
python3 scripts/sync_host_workload_guardrails.py --apply --host-root /tmp/host-workload-guardrails
```

When you are ready to update the real host, run the same command as root with the default host root `/`.
