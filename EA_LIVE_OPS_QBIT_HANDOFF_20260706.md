# EA Live Ops qBittorrent Handoff

Updated: 2026-07-06T04:51:24+02:00

## Handoff refresh (2026-07-06T04:51:24+02:00)

- The earlier follow-through items in this handoff are now landed in the worktree. Treat the older "still worth landing" section below as historical context, not as pending work.

- Repo changes now in place for this lane:
  - `scripts/materialize_qbittorrent_staging_hygiene.py`
  - `scripts/verify_qbittorrent_staging_hygiene.py`
  - `scripts/host_workload_guardrails_common.py`
  - `ops/host-workload/qbittorrent-staging-hygiene-watchdog.service`
  - `ops/host-workload/qbittorrent-staging-hygiene-watchdog.default`
  - `ops/host-workload/README.md`
  - `docs/EA_LIVE_OPS_BRIDGE.md`
  - `scripts/materialize_operator_release_dashboard.py`
  - `tests/test_qbittorrent_staging_hygiene.py`
  - `tests/test_host_workload_guardrails.py`
  - `tests/test_sync_host_workload_guardrails.py`
  - `tests/test_operator_release_dashboard_participate_billing.py`

- Behavior added by those patches:
  - qBit receipt `stdout_tail` now uses the public source label `source=script:materialize_qbittorrent_staging_hygiene.py`
  - `scripts/verify_qbittorrent_staging_hygiene.py` now rejects unsafe `stdout_tail` source paths
  - the watchdog service now supports `/etc/default/qbittorrent-staging-hygiene-watchdog`
  - repo-shipped defaults now exist in `ops/host-workload/qbittorrent-staging-hygiene-watchdog.default`
  - the operator dashboard now surfaces `dead_checking`, `requeued_meta`, `requeued_stalled`, and `requeued_checking`

- Focused validation passed after the patch set:
  - `python3 -m py_compile scripts/materialize_qbittorrent_staging_hygiene.py scripts/verify_qbittorrent_staging_hygiene.py scripts/host_workload_guardrails_common.py scripts/materialize_operator_release_dashboard.py`
  - `pytest -q tests/test_qbittorrent_staging_hygiene.py tests/test_host_workload_guardrails.py tests/test_sync_host_workload_guardrails.py -q`
  - `pytest -q tests/test_operator_release_dashboard_participate_billing.py -k 'qbittorrent_staging_hygiene or mymedia_public_surface' -q`
  - `python3 scripts/verify_host_workload_guardrails.py --repo-only`

- Current live receipt truth after refresh:
  - qBit receipt:
    - `.codex-studio/published/QBITTORRENT_STAGING_HYGIENE.generated.json`
    - `generated_at_utc=2026-07-06T02:49:14Z`
    - `runtime_status=ready`
    - `runtime_ready=true`
    - `queueing_enabled=true`
    - `dead_meta_candidate_count=0`
    - `dead_stalled_candidate_count=0`
    - `dead_checking_candidate_count=0`
    - `orphan_partial_file_count=0`
    - `torrent_count=1`
    - `state_counts={stoppedUP:1}`
  - qBit verifier:
    - `status=pass`
    - `failures=[]`
  - operator dashboard:
    - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T02:49:15Z`
    - qBit lane is present as:
      - `qbittorrent staging hygiene: ready=true status=ready orphan_partials=0 orphan_partial_gib=0 dead_meta=0 dead_stalled=0 dead_checking=0 requeued_meta=0 requeued_stalled=0 requeued_checking=0 advisory=none`
      - `qbittorrent staging hygiene verifier: structural_status=pass runtime_status=ready`
    - dashboard overall still fails for unrelated release blockers, not for the qBit lane:
      - release channel still `preview`
      - Windows installer visual proof still missing/mismatched for promoted digest `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`

- Safe guidance for the next codex:
  - do not reopen this lane as a speculative fix target; the current qBit/operator-receipt path is green
  - if you need to touch host workload rollout next, focus on syncing/enabling the shipped watchdog defaults on the host rather than changing receipt logic again
  - if you need a live confidence refresh, rerun:
    - `python3 scripts/materialize_qbittorrent_staging_hygiene.py --timeout-seconds 10 --min-dead-stalled-age-minutes 30 --apply-requeue-dead-stalled-downloads --apply-delete-dead-stalled-downloads --apply-requeue-dead-meta-downloads --apply-delete-dead-meta-downloads --apply-requeue-dead-checking-downloads --apply-delete-dead-checking-downloads --max-recovery-cycles 2 --recovery-wait-seconds 3`
    - `python3 scripts/verify_qbittorrent_staging_hygiene.py --receipt .codex-studio/published/QBITTORRENT_STAGING_HYGIENE.generated.json`
    - `python3 scripts/verify_host_workload_guardrails.py --repo-only`

This handoff is for other codex workers touching the EA live-ops / host-workload / qBittorrent lane.

## Live truth

- The live qBittorrent staging-hygiene receipt was refreshed and verified during this pass:
  - materialize:
    - `python3 scripts/materialize_qbittorrent_staging_hygiene.py --timeout-seconds 10 --min-dead-stalled-age-minutes 30 --apply-requeue-dead-stalled-downloads --apply-delete-dead-stalled-downloads --apply-requeue-dead-meta-downloads --apply-delete-dead-meta-downloads --apply-requeue-dead-checking-downloads --apply-delete-dead-checking-downloads --max-recovery-cycles 2 --recovery-wait-seconds 3`
  - verify:
    - `python3 scripts/verify_qbittorrent_staging_hygiene.py --receipt .codex-studio/published/QBITTORRENT_STAGING_HYGIENE.generated.json`
- Current published receipt:
  - `.codex-studio/published/QBITTORRENT_STAGING_HYGIENE.generated.json`
  - `generated_at_utc=2026-07-06T02:43:58Z`
  - `runtime_status=ready`
  - `runtime_ready=true`
  - `queueing_enabled=true`
  - `dead_meta_candidate_count=0`
  - `dead_stalled_candidate_count=0`
  - `dead_checking_candidate_count=0`
  - `orphan_partial_file_count=0`
  - `torrent_count=1`
  - `state_counts={stoppedUP:1}`
- Current verifier output:
  - `status=pass`
  - `failures=[]`

## Code already in the worktree

- The recovery lane itself is already meaningfully ahead of the last clean base in:
  - `scripts/materialize_qbittorrent_staging_hygiene.py`
  - `tests/test_qbittorrent_staging_hygiene.py`
- Treat those files as the current source of truth before editing. The important behavior already present there:
  - dead-stalled detection includes long-inactive zero-speed `downloading` / `forcedDL`
  - dead metadata recovery/delete path exists
  - long checking recovery/delete path exists
  - recovery flow is `pause -> reannounce -> resume -> recheck`
  - requeued downloads are filtered so they do not immediately reappear as dead-stalled in the same run

## Focused validation already completed

- `pytest -q tests/test_qbittorrent_staging_hygiene.py -q`
- `python3 -m py_compile scripts/materialize_qbittorrent_staging_hygiene.py`
- live materialize/verify commands above

## Historical follow-through that was pending at 2026-07-06T04:44:13+02:00

1. Secret-safe receipt parity
   - Files:
     - `scripts/materialize_qbittorrent_staging_hygiene.py`
     - `scripts/verify_qbittorrent_staging_hygiene.py`
     - `tests/test_qbittorrent_staging_hygiene.py`
   - Goal:
     - add `source=script:materialize_qbittorrent_staging_hygiene.py` to `stdout_tail`
     - make the verifier reject unsafe `stdout_tail` source paths like:
       - `source=/docker/.../materialize_qbittorrent_staging_hygiene.py`
     - mirror the pattern already used by:
       - `scripts/verify_ea_operator_readiness.py`
       - `scripts/verify_mymedia_public_surface.py`

2. Reusable watchdog configuration surface
   - Files:
     - `ops/host-workload/qbittorrent-staging-hygiene-watchdog.service`
     - add `ops/host-workload/qbittorrent-staging-hygiene-watchdog.default`
     - `scripts/host_workload_guardrails_common.py`
     - `tests/test_host_workload_guardrails.py`
     - `tests/test_sync_host_workload_guardrails.py`
     - `ops/host-workload/README.md`
     - optionally `docs/EA_LIVE_OPS_BRIDGE.md`
   - Goal:
     - load an env/default file through the service instead of burying all runtime tuning in the shell script
     - preferred default posture:
       - `QBIT_ENSURE_QUEUEING=1`
       - keep dead-stalled delete on
       - leave meta/checking delete conservative unless you intentionally change policy

3. Operator dashboard visibility
   - Files:
     - `scripts/materialize_operator_release_dashboard.py`
     - `tests/test_operator_release_dashboard_participate_billing.py`
   - Goal:
     - extend the qBit summary line so operators can see:
       - `dead_checking`
       - `dead_meta_requeue_count`
       - `dead_stalled_requeue_count`
       - `dead_checking_requeue_count`
     - keep the lane non-release-blocking

## Worktree cautions

- `scripts/materialize_operator_release_dashboard.py` is heavily modified in the current worktree. Reread it live and patch surgically.
- `tests/test_operator_release_dashboard_participate_billing.py` drifted enough that a combined broad patch failed on anchor mismatch. Split edits into smaller steps.
- `ops/host-workload/README.md` already has in-flight edits in the worktree. Do not assume the base version from memory.

## Recommended next command sequence

1. `sed -n '1,220p' scripts/verify_qbittorrent_staging_hygiene.py`
2. `sed -n '996,1045p' scripts/materialize_qbittorrent_staging_hygiene.py`
3. `sed -n '1,220p' scripts/host_workload_guardrails_common.py`
4. `sed -n '1,220p' tests/test_host_workload_guardrails.py`
5. `sed -n '1,220p' tests/test_sync_host_workload_guardrails.py`
6. `sed -n '3528,3570p' scripts/materialize_operator_release_dashboard.py`
7. `rg -n "qbittorrent staging hygiene|QBITTORRENT_STAGING_HYGIENE" tests/test_operator_release_dashboard_participate_billing.py`

Then patch in that order and re-run only the focused tests you changed.
