# Rejoin after disconnect

Status: preview

## User goal

Lose connectivity or switch devices during live play, then rejoin the session without the table reconstructing truth by memory.

## Entry surfaces

* `chummer6-mobile` live play shell
* Hub-backed session and relay surfaces

## Happy path

1. The play shell preserves the last safe local ledger and session context.
2. On reconnect, mobile asks Hub for the current session projection and replay-safe catch-up data.
3. Core-backed semantics and play contracts restore the session without inventing a second event family.
4. The user gets a reconnect replay summary and resumes play on the current device.

## Failure modes

* If shared-state confidence breaks, the shell must surface stale or conflict state instead of silently merging.
* If replay data is incomplete, the user must see that continuity is degraded and which recovery path is still legal.
* If reconnect would widen ownership by reimplementing engine or hub semantics locally, the reconnect must stop and the boundary issue must be fixed upstream.

## Success evidence

* Replay-safe reconnect is boringly reliable across devices.
* Shared-state drift is observable and receipt-backed.
* Resume remains inside mobile and hub ownership while consuming core truth.

## Canonical owners

* `chummer6-mobile`
* `chummer6-hub`
* `chummer6-core`
