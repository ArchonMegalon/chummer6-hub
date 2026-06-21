# Privacy and retention boundaries

## Purpose

This file defines the default privacy, retention, and redaction rules for Chummer product and support systems.

It exists so support, crash, install-linking, survey, assistant, and external-service data do not silently turn into a pile nobody understands or needs.

The product-steering telemetry model and concrete opt-out event schema that sit inside these boundaries are defined in `PRODUCT_USAGE_TELEMETRY_MODEL.md` and `PRODUCT_USAGE_TELEMETRY_EVENT_SCHEMA.md`.
User-contribution privacy, IP, and visibility rules for BLACK LEDGER intel, house-rule submissions, open-run applications, session debriefs, media artifacts, public feedback, and creator submissions are defined in `USER_CONTRIBUTION_PRIVACY_AND_IP_POLICY.md` and `USER_CONTRIBUTION_VISIBILITY_REGISTRY.yaml`.

## Default rules

* retain the smallest record that still lets support close an issue honestly
* keep install-local secrets, raw auth tokens, updater rollback payloads, and local caches on the install unless a reviewed Chummer feature needs a saved summary
* prefer short structured summaries over keeping raw payloads indefinitely
* external-service data must be redacted before it is saved unless the owning feature explicitly says otherwise
* every saved data type needs an owner, a retention clock, redaction rules, and a delete-or-summarize rule

## Retention domains

### Support cases

Owner: `chummer6-hub`

Retention:

* case timeline and user-visible status events: retain for 18 months after the last state change
* public known-issue links and closure records: retain for 18 months after public closure
* raw attachments that are no longer needed for open investigation: summarize or redact within 90 days

Redaction baseline:

* remove secrets, local paths, and unrelated identity data from user-visible case history
* preserve the install, channel, and version details needed for honest fix-availability notices

### Crash envelopes

Owner: `chummer6-hub`

Retention:

* raw crash envelopes: retain for 90 days unless tied to an active blocker or open case cluster
* normalized crash signatures and clustered records: retain for 18 months
* local crash dumps remain install-local unless explicit user action uploads them

Redaction baseline:

* no raw secrets, tokens, or local machine credentials in retained crash payloads
* strip or hash install-local absolute paths when they are not required for a live investigation

### Claim and install linkage

Owner: `chummer6-hub` plus `chummer6-hub-registry`

Retention:

* claim tickets and install-link events: retain for 365 days after last install activity
* durable install identity, channel, and last-seen release status: retain while the install relationship remains active
* superseded claim files should collapse into one current install record plus limited historical records

Redaction baseline:

* never persist personalized binary data because the published binary stays the same for everyone
* keep person, install, device-role, and campaign scopes explicit instead of flattening them into a single sync blob

### Product usage telemetry

Owner: `chummer6-hub` plus `fleet`

Retention:

* raw hosted product-improvement event envelopes: retain for 30 days or less, then collapse into daily rollups
* install-linked daily usage rollups: retain for 18 months
* explicit debug-uplift telemetry tied to a support case or beta investigation: retain only while the case or investigation is active, then delete or summarize within 30 days

Redaction baseline:

* retain package IDs, fingerprints, buckets, and counters instead of raw character content, campaign content, or houserule bodies
* no character names, campaign names, notes, free text, or full custom-data blobs in the default hosted telemetry plane
* install-linked telemetry is opt-out by default, pseudonymous by default, and must not be repurposed as a marketing profile

### Survey and follow-up results

Owner: `chummer6-hub`

Retention:

* post-fix follow-up invites and answer summaries: retain for 365 days
* raw free-text survey payloads: summarize or redact within 180 days unless still tied to open product work

Redaction baseline:

* keep survey conclusions out of public guide copy until they are reviewed
* redact install/account data that is not required for the follow-up question being answered

### Help and assistant service traces

Owner: `executive-assistant` plus the owning product surface

Retention:

* raw external-service request/response traces: retain for 30 days unless a narrower service contract says less
* help summaries, comparison notes, and review notes: retain for 180 days
* promoted help, support, and public answers must be rebuilt from reviewed Chummer sources, not from indefinite external-service transcripts

Redaction baseline:

* no unlimited PII spill into service prompts, logs, or review traces
* help summaries should prefer case IDs, release IDs, and rule explanation IDs over raw user text where possible

### User contribution and external workbench summaries

Owner: `chummer6-hub`

Retention:

* Teable/AdminIntent rows: retain only while the source queue item is active, then collapse into admin history
* raw user-contribution payloads in external intake tools: mirror needed records into Hub, then summarize or delete from the external tool according to the contribution class
* public-safe contribution summaries and credit records: retain while the contribution is published plus 18 months

Redaction baseline:

* never collect raw sourcebook text, private table spoilers, faction secrets, or support notes into public or vendor-visible contribution queues unless a Hub-owned projection explicitly permits the field
* private submissions must move through visibility classes before becoming public lore, job seeds, map markers, videos, newsletters, or Signitic/Emailit campaign payloads

### Publication files and media data

Owner: `chummer6-media-factory` plus `chummer6-hub-registry`

Retention:

* file manifests, provenance records, and compatibility records: retain while the file remains published plus 18 months
* stale previews and revoked files: keep the record chain, but purge superseded raw render intermediates within 90 days

Redaction baseline:

* public trust surfaces should expose provenance and moderation state, not hidden staff notes or raw external-service payloads

## Surface redaction rules

### Public surfaces

* may expose support status, known issues, release status, compatibility, provenance, and channel-aware fix availability
* may not expose private case notes, raw crash envelopes, external-service traces, or account-internal survey payloads

### Signed-in user surfaces

* may expose case timeline, install status, claimed-device state, and the user-safe slice of crash/support data
* may not expose unrelated reporter data, staff-only deliberation, or private moderation notes

### Staff surfaces

* may access the limited records needed for reroute, freeze, release, or close decisions
* must still prefer redacted or summarized payloads over indefinite raw-body retention

### Help and assistant surfaces

* must base answers on reviewed Chummer sources, release records, or support-case records
* must not become the system of record for support or release state

## Repo ownership split

* `chummer6-hub` owns user-visible support, case, survey, and install-link retention records
* `chummer6-hub-registry` owns install/update/release/public-trust summaries that depend on retained release records
* `fleet` owns limited incident and publish-history evidence, not the whole-user record
* `executive-assistant` owns route-steering traces and help summaries, not public or support system-of-record semantics
* `chummer6-media-factory` owns render records, preview supersession, and revoked file handling

## Release rules

* a surface that persists raw secrets, raw external-service traces, or undefined retention windows fails release signoff
* a new assistant/help/external-service integration must declare redaction and retention rules before it can be promoted
* product review may freeze a wave when retention or privacy rules drift behind shipped user trust claims
* any new contribution, Teable, Emailit, Signitic, ProductLift, Icanpreneur, Hedy, Nonverbia, Unmixr, or Deftform workflow must declare contribution class, visibility class, redaction rules, and delete-or-summarize rule before promotion
