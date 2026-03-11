# Multi-Head Parity Audit

Date: 2026-03-04
Scope: shared behavior parity across `Chummer.Blazor` and `Chummer.Avalonia` over `Chummer.Run.Api` + `Chummer.Presentation`

## Current status

- The Docker branch is the current multi-head runtime for this repository.
- `Chummer.Run.Api` remains a thin host with workspace-focused endpoints.
- `Chummer.Blazor` and `Chummer.Avalonia` both render shared presenter state.
- The checked-in parity oracle (`docs/PARITY_ORACLE.json`) now captures the cross-head surface contract without requiring `Chummer.Web` artifacts at test time.
- `Chummer.Web`, the `chummer-web` runtime service path, and legacy HTML-derived parity extraction are decommissioned from runtime-critical flows.
- Architecture/compliance tests and Linux docker migration loop are green.

## Primary risk

Execution drift, not architecture shape:

1. The shared presenter seam can regress into a monolith if responsibilities are not split aggressively.
2. Shell/session behavior can drift between heads if command/tab/action enablement is duplicated.
3. Workspace internals are still XML-shaped and need to be pushed to import/export edges.

## Required parity gates

Run:

```bash
bash scripts/ai/verify.sh
```

## Migration direction

- Keep one shell contract and one behavior path in `Chummer.Presentation`.
- Keep both heads thin and renderer-oriented.
- Complete parity by tab family via `/api/workspaces/{id}/sections/{sectionId}`.
- Add explicit save/download/export semantics and reduce XML coupling.
- Track all work as issue-sized slices in `docs/MIGRATION_BACKLOG.md`.
