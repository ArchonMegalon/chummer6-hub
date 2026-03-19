# Hosted Restore Runbook

Purpose: keep the hosted share of `F1` explicit and runnable.

This runbook is the operator-facing proof path for session-ledger restore, registry/runtime-bundle restore, and replay-safe counter continuity in the hosted runtime after contract and owner-repo extraction.

## Scope

This drill covers:

- session-ledger backup and restore continuity
- registry artifact/install/review/runtime-bundle restore continuity
- replay-safe counters for relay and registry lanes
- runtime-bundle integrity after restore

It does not claim ownership of:

- media render restore internals inside `chummer-media-factory`
- core rules truth beyond consumed contract surfaces
- browser/desktop shell recovery

## Canonical backup contracts

- session ledger: `session_state_backup_v1`
- registry store: `hub_state_backup_v1`
- focused verification runner: `scripts/ai/run_services_restore_drill.sh`

## Drill commands

Run from the repo root:

```bash
bash scripts/ai/run_services_restore_drill.sh
bash scripts/ai/run_services_smoke.sh
```

The restore drill must prove:

- session projection fingerprints and event counts survive restore
- relay observability and replay counters survive restore
- registry artifact metadata and runtime-bundle heads survive restore
- registry observability and replay counters survive restore
- legacy `hub_state_backup_v1` payloads still restore into the current store

## Restore acceptance

The hosted side of `F1` is healthy when:

- relay and registry restore drills both pass without source-owned fallback DTOs
- runtime-bundle head ownership survives restore
- replay counters survive restore for both relay and registry lanes
- the focused restore drill remains runnable separately from the full clean-room verification suite

If any of these conditions fail, the hosted share of `F1` is not closed.
