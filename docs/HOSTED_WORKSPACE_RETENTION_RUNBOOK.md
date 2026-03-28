# Hosted Workspace Retention Runbook

Purpose: keep hub-owned workspace continuity retention, cleanup, and recovery explicit instead of letting `CommunityStore` drift forever.

## Scope

This runbook covers hub-owned derived workspace continuity state:

- `RestoreByUserId` restore summaries inside `CommunityStore`
- cleanup of orphaned restore summaries after account removal
- recovery of restore summaries from durable dossier, campaign, run, and install-linking truth

It does not delete durable campaign truth:

- `RunnerDossierProjection`
- `CrewProjection`
- `CampaignProjection`
- `RunProjection`

Those records remain the long-lived continuity spine until product-level archive/delete semantics exist.

## Retention policy

- Restore summaries are derived state, not the canonical campaign record.
- Hub retains restore summaries for `30` days by default.
- Override the retention window with `CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS`.
- Any restore summary whose `GeneratedAtUtc` falls outside that window is pruned before the next account/workspace summary is materialized.
- Orphaned restore summaries are pruned immediately when the owning user no longer exists in `CommunityStore`.

## Cleanup trigger

Cleanup is enforced as a service policy, not a manual operator reminder:

- `CampaignSpineService.GetAccountSummary(...)` runs `WorkspaceLifecyclePolicyService.ApplyLocked(...)` before seeding or projecting workspace continuity state.
- If cleanup prunes stale restore summaries, the store is persisted in the same request path.
- If the active user needs a restore summary after cleanup, Hub regenerates it from durable dossier, campaign, run, and claimed-install state in the same flow.

## Recovery model

Recovery after cleanup is deliberate:

- restore summaries regenerate from durable dossier/campaign/run projections plus install-linking truth
- no secrets, grant tokens, or local caches are recovered from Hub-owned retention cleanup
- reopening `/account/work` or any campaign-workspace surface is enough to rebuild the restore packet for the affected user

## Verification proof

Run from repo root:

```bash
bash scripts/ai/run_services_verification.sh
```

The retention lane is healthy when verification proves:

- expired restore summaries are pruned
- orphaned restore summaries are pruned
- an active user immediately receives a regenerated restore summary after cleanup
- a second unchanged workspace-summary read does not rewrite the durable store again
