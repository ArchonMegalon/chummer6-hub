# Recover from sync conflict

Status: preview_and_hardening

## User goal

Recover when local and hosted session state disagree without hiding data loss or inventing a second truth system.

## Entry surfaces

* mobile local-first ledger and cache
* hub session projections and replay surfaces
* continuity and conflict recovery affordances in the play shell

## Happy path

1. The client detects divergence between local and hosted session state.
2. The shell stops ambiguous promotion and marks the state as stale or conflicted.
3. Replay and receipt-bearing evidence is fetched so the user or GM can see what diverged.
4. A legal recovery path restores one canonical session line and the shell resumes normal continuity behavior.

## Failure modes

* No silent last-write-wins merge is allowed.
* No hidden cache purge is allowed when it destroys user-visible confidence.
* Assistant-side guesses or helper summaries may explain the conflict, but they must not redefine the canonical session record.

## Success evidence

* Shared-state drift is visible rather than folklore.
* Recovery paths stay receipt-backed and replay-safe.
* Conflict handling does not widen ownership outside core, mobile, and hub seams.

## Canonical owners

* `chummer6-mobile`
* `chummer6-hub`
* `chummer6-core`
