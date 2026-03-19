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
| WL-233 | done | P1 | Close `C1b` by inventorying every live orchestration-side external adapter, moving any stray client/provider ownership out of downstream repos, and proving hub-only adapter authority. | agent | Closed 2026-03-19: `HOSTED_ADAPTER_AUTHORITY.md` plus hosted verification now inventory live provider, research, prompt/help, approval-gated automation, operator, interop, and director-intake seams, while future survey/feedback/docs-help SaaS adapters remain explicitly absent rather than leaking into client-owned authority. |
| WL-234 | done | P1 | Close `E2` and `E2b` for hub by proving publication/install/review/discovery, docs/help, feedback loops, and operator projections are coherent consumer surfaces rather than hidden write-owning side systems. | agent | Closed 2026-03-19: registry owner proof is controller-backed in `chummer6-hub-registry`, and hosted verification now locks docs/help, advisory feedback, and operator boards to consumer-only seams instead of parallel write-owning state. |
| WL-235 | done | P1 | Close `E3` by making Coach, Spider, and Director governance, grounding, approval posture, and reviewability explicitly executable in the hosted verification path. | agent | Closed 2026-03-19: `ASSISTANT_PLANE_AUTHORITY.md` plus hosted verification now keep Coach, Spider, and Director governance, grounding, approval-aware action rails, and observability explicit and executable. |
| WL-236 | done | P1 | Close the hosted share of `F1` by publishing concrete observability, DR, restore, and replay-safety operator evidence for hub runtime flows. | agent | Closed 2026-03-19: `HOSTED_RESTORE_RUNBOOK.md` and `scripts/ai/run_services_restore_drill.sh` now make session-ledger and registry restore continuity runnable outside the full verification sweep. |
| WL-231 | done | P1 | Keep `Chummer.Media.Contracts` physically separated from hosted ownership by moving any repo-local contract copy into explicit compatibility wrappers only. | agent | Closed 2026-03-19: the orphaned repo-local `Chummer.Media.Contracts` source project was deleted, hosted verification now rejects any regrowth, and the expected owner-repo seam is documented in `docs/HOSTED_BOUNDARY.md` and `docs/HUB_EXTRACTION_ACCEPTANCE.md`. |
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

- Repo-local live queue: none
- Registry/media ownership, contract canon, orchestration-side adapter authority, hub-side product-consumer planes, and assistant-plane governance are verifier-backed and materially closed.
- Remaining repo work is future product depth and physical cleanup, not missing hosted-boundary authority proof.

## Historical log

- Full queue-overlay churn, duplicate publication notes, and re-entry proof now live in `RECONCILIATION_LOG.md`.
