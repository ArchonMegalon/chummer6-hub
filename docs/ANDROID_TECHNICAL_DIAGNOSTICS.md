# Android technical diagnostics

This is bounded support intake, not an analytics product or crash/ANR detector.
The Hub service owns the short-lived receiving store. Android owns collection,
disclosure, explicit tester opt-in and its bounded offline queue. Merely deploying
this server code does not enable collection on a phone or notify an operator.

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

The feature is off by default. Set all of the following in private local Docker
configuration, never in a repository, image or distributed client:

- `CHUMMER_ANDROID_DIAGNOSTICS_ENABLED=true`
- `CHUMMER_ANDROID_DIAGNOSTICS_DIRECTORY`: absolute private writable directory,
  mode 0700 on Linux, without symlink ancestry; mount separately from account
  state and outside backup/Teable export paths.
- `CHUMMER_ANDROID_DIAGNOSTICS_READER_TOKEN`: dedicated random 32–256 character
  printable ASCII reader credential. Do not reuse an account or Fleet credential.

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

Before enabling on real phones: admit the exact Control package, connect the
opt-in Android sender, verify a synthetic POST and authorized readback, reconcile
the live privacy/Play Data Safety disclosures, and verify withdrawal/offline
behavior. Operator notification is a separate integration, not implied by 202.
The reported reload-only-recovers-after-navigation defect remains a separate
product investigation; these diagnostics do not establish that it is fixed.
