# Worklist Queue

Purpose: keep the live hosted-boundary queue readable. Historical re-entry and queue-publication churn now live in `RECONCILIATION_LOG.md`.

## Status Keys
- `queued`
- `in_progress`
- `blocked`
- `done`

## Queue
| ID | Status | Priority | Task | Owner | Notes |
|---|---|---|---|---|---|
| WL-231 | queued | P1 | Keep `Chummer.Media.Contracts` physically separated from hosted ownership by moving any repo-local contract copy into explicit compatibility wrappers only. | agent | Publish the expected ownership boundary into `docs/HOSTED_BOUNDARY.md` and verification evidence so no hosted code path can be mistaken for persistent media contract truth. |
| WL-232 | done | P1 | Add transport-wrapper evidence for `Play` and `Run` seams to prove runtime/protocol ownership moved to `chummer6-mobile` and `chummer6-core` respectively. | agent | Closed 2026-03-18: `Chummer.Play.Contracts` now owns the shared play/session transport DTOs, `Chummer.Run.Contracts` no longer shadows relay/spider/docs/interop families, compatibility checks assert the duplicate hosted namespaces are gone, and verification keeps the `/api/play/*` seam and run-only backup/ingestion contracts explicit. |
| WL-216 | done | P1 | Materialize explicit backlog/evidence anchors for `A2` and `A3` contract canon lanes. | agent | Closed 2026-03-13: hosted/play/run contract canon anchors now exist in `docs/HUB_EXTRACTION_ACCEPTANCE.md` and the verification suite keeps them executable. |
| WL-217 | done | P1 | Materialize orchestration-side external-adapter acceptance anchors (`C1b`). | agent | Closed 2026-03-13: the hub boundary now documents receipt, kill-switch, and adapter expectations instead of relying on folklore. |
| WL-218 | done | P1 | Materialize session semantic canon acceptance anchors (`D1`). | agent | Closed 2026-03-13: session-semantic canon is explicitly tracked as shared truth between hub, core, and mobile instead of being buried in queue prose. |
| WL-219 | done | P2 | Materialize docs/feedback/operator projection acceptance anchors (`E2b`). | agent | Closed 2026-03-13: projection-plane work is explicit and hosted-boundary-safe. |
| WL-220 | done | P2 | Materialize observability / DR / replay-safety hardening anchors (`F1`). | agent | Closed 2026-03-13: the hosted hardening lane now points at concrete runbook and verification evidence. |
| WL-227 | done | P1 | Archive reconciliation/publication churn out of the live hosted queue. | agent | Completed 2026-03-14: the old worklist was preserved in `RECONCILIATION_LOG.md`, and this file now reflects the current hosted boundary instead of every duplicate queue-overlay echo. |
| WL-228 | done | P1 | Materialize milestone mapping for legacy desktop/tooling root clutter in hosted repo boundary work (`C2` / `R0`). | agent | Completed 2026-03-14: mapped candidates `21818` and `53655` to the already-executed `WL-207`, `WL-209`, `WL-210`, `WL-211`, and `WL-212` lane in `docs/HUB_EXTRACTION_ACCEPTANCE.md`, with executable verification anchored in `HubExtractionReadinessVerification.cs` and `scripts/ai/verify.sh`. |
| WL-229 | done | P1 | Reconcile repeated add-mapping queue publication for legacy desktop/tooling root clutter against existing `WL-228` mapping coverage. | agent | Completed 2026-03-14: incorporated unread feedback `2026-03-13-162336-audit-task-8698.md` then `2026-03-13-162336-audit-task-27.md`, confirmed `WL-228` and `docs/HUB_EXTRACTION_ACCEPTANCE.md` already keep this `C2`/`R0` lane executable, and removed only the duplicate stale add-mapping overlay prompt from `.codex-studio/published/QUEUE.generated.yaml`. |
| WL-230 | done | P1 | Reconcile system re-entry slice to publish/append runnable backlog for the missing `Chummer.Media.Contracts` package seam. | agent | Completed 2026-03-14: incorporated unread feedback in order (`2026-03-13-162336-audit-task-2369.md`, then `2026-03-13-162336-audit-task-21924.md`), confirmed `.codex-studio/published/QUEUE.generated.yaml` already contains the exact runnable-backlog prompt (plus add-mapping companion) for this seam, and kept queue contents unchanged to avoid duplicating already-published backlog work. |

## Current repo truth

- Repo-local live queue: `WL-231` only
- Remaining blockers are structural, not hidden local TODOs: `A2`, `A3`, `C0`, `C1`, `C2`, and `D1` remain open in central design truth until registry/media ownership and semantic canon are fully cut over
- The repo still needs to get physically smaller before the README claim “orchestrator, not hidden super-repo” becomes fully credible

## Historical log

- Full queue-overlay churn, duplicate publication notes, and re-entry proof now live in `RECONCILIATION_LOG.md`.
