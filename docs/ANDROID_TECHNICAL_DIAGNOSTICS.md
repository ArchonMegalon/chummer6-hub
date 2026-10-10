# Android technical diagnostics

This is bounded support intake, not an analytics product or crash/ANR detector.
The Hub service owns the short-lived receiving store. Android owns collection,
disclosure, tester control and its bounded offline queue. Merely deploying
this server code does not enable collection on a phone or notify an operator.
The user-approved Internal build policy defaults sending ON only when no saved
choice exists. A saved OFF choice survives updates and restart; corrupt or
unavailable choice storage cannot enable sending. Development/public builds
default OFF. Internal binaries must be explicitly built for that channel, not
promoted unchanged to public distribution. Settings explain collection and allow
immediate disabling and queue clearing; old local observations are not replayed.

## Contract

`Chummer.Control.Contracts.Support.AndroidDiagnosticReport` is the canonical
contract. Do not copy its DTO source into a client. It contains only a random
per-report idempotency ID, app version code, observation time, fixed area/action/
outcome/error enums and elapsed milliseconds. Every field is required. Unknown
fields, invalid enum values and invalid timestamps are rejected. There is no
account, device, runner or book identity, free text, exception message, stack,
screenshot, URL or arbitrary metadata dictionary.

`Slow` means an observed long-running action, not a proven product failure or
Android ANR. Intake is anonymous and therefore untrusted: counts must not be
presented as verified users, unique devices, causal diagnoses or release gates.

## Activation and private reading

The **server intake** is off by default. Set all of the following in private local Docker
configuration, never in a repository, image or distributed client:

- `CHUMMER_ANDROID_DIAGNOSTICS_ENABLED=true`
- `CHUMMER_ANDROID_DIAGNOSTICS_DIRECTORY`: absolute private writable directory,
  mode 0700 on Linux, without symlink ancestry; mount separately from account
  state and outside backup/Teable export paths.
- `CHUMMER_ANDROID_DIAGNOSTICS_READER_TOKEN_FILE`: absolute read-only mounted
  file containing a dedicated random 32–256 character printable ASCII reader
  credential (optional final LF/CRLF). Local Linux x64 verifies owner-only file
  permissions, file type and bounded length, rejecting symlink ancestry and a
  group/world-writable parent. Use mode 0600 owned by the container UID, outside the report
  volume, web roots and backup/export paths. Do not reuse account/Fleet secrets.
  `CHUMMER_ANDROID_DIAGNOSTICS_READER_TOKEN` remains a direct configuration
  alternative for isolated tests; never configure both. Disabled intake does not
  read or require a credential file. Credential failures must not be logged with
  contents or authorization headers.

Only one writer may use the volume. It must not be a downloads/web directory.
Keep the production endpoint behind the existing HTTPS ingress and Hub request
guardrails. Do not log request bodies or authorization headers at an edge/proxy.
Do not copy the short-lived snapshot into durable support cases, Telegram, public
issues or append-only storage automatically. Normal ingress connection metadata
is outside this store and remains subject to the deployment's privacy policy.

`POST /api/v1/support/android-diagnostics` accepts at most 2048 bytes and returns
202 with only report ID and receipt time, after atomic local persistence. An
identical retry returns the original receipt. A conflicting ID returns 409;
invalid metadata returns 400. The global store admits at most 64 new reports per
hour and 512 retained reports / 256 KiB; capacity returns 429 with Retry-After.
Clients must retain an uncertain report's ID, respect backoff, and never replay
with a fresh ID merely because a response was lost.

`GET` on the same route requires the separate `Authorization: Bearer` reader
credential. It returns a bounded private readback, not a public dashboard. Both
routes use `Cache-Control: no-store`. Disabled or unavailable/corrupt storage
returns 503; it never silently overwrites corrupt evidence with an empty store.

Reports expire two days after receipt. Reads and submissions exclude expired
records; maintenance deletes them on startup and every 15 minutes while the
service is running. An offline/stopped volume cannot delete itself: on recovery,
run retention before exporting/reading, and do not retain volume backups.
This deliberately ephemeral store is not account recovery authority.

## Delivery boundary

`scripts/android_diagnostic_alerts.py` is an optional, separate private Docker
worker. It reads the bounded inbox once per minute with the dedicated reader;
no account credentials or Docker socket are mounted. Its scoped Telegram bot and
private recipient must be provisioned from the existing live EA connector binding,
never from a test binding or a hardcoded chat fallback. It verifies the actual bot
and private chat through Telegram before a send. It does not start EA services.

Only allowlisted version/category/outcome/error counts are sent, without report
IDs, raw observations or character/account content. Counts are reports, not users;
slow observations are explicitly not classified as ANRs. The first poll baselines
existing reports without notifying. New reports are batched with a 15-minute
cooldown, at most four attempts/hour and twelve/day. Nothing is sent for quiet
polls. This is not a guarantee that every failure produces a message.

Private worker state contains only hashed deduplication IDs (two-day expiry),
bounded attempt times and a coarse outcome. Mount `/state` mode 0700 outside
backups and Teable; files are owner-only and bounded at 64 KiB. A send is claimed
durably before the network request. Lost/ambiguous responses are not replayed,
including after restart; they require manual investigation. Corrupt state fails
closed, not as an empty outbox. Telegram may retain the category-only message;
the two-day raw-report retention promise does not apply to those summaries.

Deduplication history is independent of the receiver's latest snapshot: an
inbox reset or temporarily absent report does not erase an unexpired claim.
Existing claims retain their original receipt timestamps when IDs reappear.
The worker retains at most 512 hashed IDs. If a new batch would exceed that
bound, it logs `dedup_saturated_no_send`, defers the whole batch without a send
attempt, and preserves every unexpired claim. Normal two-day expiry frees room;
the worker never evicts claims to make space. Deferred reports may themselves
expire or disappear from the ephemeral inbox, so this prioritizes suppression
of repeat/uncertain sends over guaranteed notification delivery.

Before enabling on real phones: admit the exact Control package, connect the
Internal-channel Android sender, verify a synthetic POST and authorized readback, reconcile
the live privacy/Play Data Safety disclosures, and verify withdrawal/offline
behavior. Operator notification is a separate integration, not implied by 202.
The reported reload-only-recovers-after-navigation defect remains a separate
product investigation; these diagnostics do not establish that it is fixed.
