# Teable primary migration — in progress

The user's 2026-09-23 decision makes Teable the primary working store for the
fresh Hub account and Origin book/job state. This is not a backup/projection.
Production has **not** been cut over. The original encrypted Docker volume is
preserved; none of its unreadable records were decrypted or silently imported.

## Implemented

- `Chummer.Storage.Teable` owns the shared revision transport and private Linux
  credential-file reader. API and Identity reference that single implementation.
- Immutable bounded chunks and a unique successor manifest provide compare-and-
  exchange admission. Lost acknowledgements are reconciled without POST replay.
- Install-linking and Data Protection have explicit production primary
  registrations. Startup proves remote key custody with two independent provider
  instances. Deep readiness checks the remote key repository, not a local key
  directory. Account snapshots restore from the primary into a disposable,
  protected local mirror; readiness rejects a mirror behind the remote head.
  Competing PostgreSQL/certificate configuration is rejected. This registration
  is implemented and tested, **not deployed**.
- Identity has an explicit Teable primary mode. Sessions, subject roles, hashed
  email tickets and recipient throttling state are remote, not local mirrors.
  Every authorization reads current primary state. Conflicting/uncertain writes
  disable that service instance until cold reconciliation; it cannot authorize
  from mutated memory. Backend failure never falls back to local account files.
- Email ticket consumption and session issuance share one commit. Competing
  consumers cannot both issue an admitted session.
- Origin chapters have independent remote revision streams and a bounded opaque
  discovery catalogue. Sources, returned prose, worker admissions and reader
  acceptance survive cold restore without a local book file. Registration precedes
  job creation; an interrupted reservation is inert. Competing admissions cannot
  both grant generation permission, and an ambiguous acknowledgement leaves the
  existing dispatch for reconciliation, never automatic paid resubmission.
- Private first-party documents now also have a primary mode. The actual
  metadata, Markdown, JSON, preview receipt and export receipt live remotely;
  reading/downloading them creates no local artifact directory. The same
  owner/input/content validator is used for both backends. An opaque bounded
  catalogue reserves capacity before document creation. Only the one-time export
  receipt can be added to an immutable document revision. Conflicts require a new
  read; lost commit acknowledgements can be reconciled without another write.
  These are existing first-party drafts, **not generated First Book narration**.
- Linked runner snapshots now have an explicit primary mode, with a separate
  revision stream for each exact subject/user owner. Full Core continuations,
  auxiliary state and finalization history restore without a local snapshot
  file. Each outer synchronous owner scope reads current remote state and drops
  its mutable shadow when it ends. Concurrent writes require a fresh read;
  lost acknowledgements never trigger write replay. Observed revision floors
  survive owner switches. Remote outages/invalid state return 503 and conflicts
  return 409, without a local-file fallback. Existing local mode is unchanged.
- MyFirstBook monthly usage and Origin provider-credit reservations have explicit
  primary registrations. Each ledger has its own revision stream/schema and
  private token configuration. Fresh outer scopes restore all rows from Teable;
  nested scopes retain pending edits and scope exit clears primary mutable state.
  Invalid rows, duplicate allowance windows/reservations and regressed revisions
  reject without resetting allowance. Quota is rechecked against the current
  write-scope snapshot, with compare-and-exchange protecting competing instances.
  An acknowledged consumption returns its committed count without a second remote
  response read. Failed persistence rolls back the in-memory candidate in local
  mode too. Reservations remain credit holds, not an exactly-once provider-dispatch
  authorization; chapter/job admissions still own paid dispatch. No new automatic
  mutation retry, client-request idempotency or cross-ledger transaction is claimed.
- Billing membership snapshots now also have an explicit primary registration.
  Member ID/email, plan/status and observation/sync timestamps persist remotely.
  Sync authentication and plan/status admission happen before accessing the store.
  Reads always enter a fresh remote scope, including email fallback and quota
  derivation; there is no stale-memory or local-file membership fallback. Restore
  uses the same supported/active-status configuration and canonical plans as sync.
  Inconsistent or duplicate rows fail instead of inferring an entitlement. Changed
  status policy requires reconciliation. A failed local sync no longer leaves an
  uncommitted upgrade in memory. This is private billing-state custody, not a live
  billing-provider integration, new entitlement source or payment proof.
- Horizon weekly usage and request receipts now have explicit primary modes.
  Cold reads restore allowance counts and accepted/blocked request metadata,
  including governed render bindings, without creating local files. Conflicting
  writes require a fresh read; uncertain receipt writes are reconciled by reading,
  not replaying consumption. Hostile identity/status/quota bindings fail closed.
  Restored render requests do not activate a provider or assert rendered output.
  Monthly multi-unit consumption is now one allowance commit, not a loop that
  can partially charge a request. Weekly allowance checks also reject integer
  overflow. Charged requests now store their receipt inside the same weekly or
  monthly usage commit: no second receipt write can fail after the charge.
  Cold lookup/listing combines those receipts with the legacy/compose-only store.
  Duplicate charge identities reject before consuming again. Unknown outcomes
  require readback, not replay. This closes the charge/receipt gap for new
  requests; it is not an end-to-end provider-dispatch transaction or a new
  client idempotency contract.
- Community profiles, principal mappings and groups now have an isolated primary
  implementation using the existing typed snapshot. Explicit synchronous scopes
  refresh at outer entry; nested account/group/identity-link/ledger/experience
  operations retain that snapshot. Conflicting or uncertain writes disable the
  instance. Unconverted legacy `Gate` callers and local-file consumers reject
  primary mode rather than using stale authorization or creating a local shadow.
  Recognition/leaderboards and the operator user projection now read from explicit
  current scopes. Public profile opt-out is observed on the next read. Community,
  Passport, Signal Deck and Living World summary composition captures Community
  counts together before touching installation/publication dependencies; it no
  longer reads notification counts outside the Community scope. No scope crosses
  an asynchronous projection call, and no external projection is enabled here.
  Faction onboarding also resolves state from the current scope instead of a
  constructor-cached reference. Charter/allegiance admission, action allowance
  and receipt writes, moderation and private lore use fresh revision admission.
  Each mutation retains one synchronous outer scope across its validation and
  commit; nested domain reads cannot replace pending state. Campaign summary
  dependencies are not thereby declared fully migrated.
  Sponsor intents, consent and account-facing queries also use current scopes.
  A Fleet GET observation carries only a detached snapshot/fingerprint across
  the wait, then re-reads and compares the complete stored session and account.
  Changed ownership/state, terminal sessions and a different returned lane reject
  before applying the reply. Consent cannot reopen stopped/revoked sessions or
  reset an already-consented session. Primary mode never auto-activates Fleet.
  Fleet creation, device auth, activation and stop/delete remain explicitly
  unavailable in primary mode pending durable operation fencing/reconciliation.
  This is a read/intent migration, not complete sponsor-operation support; the
  remaining legacy external-write paths still require that conversion.
  Campaign recap/replay metadata now shares the Community primary revision with
  its aftermath projection. Registration refreshes the Registry-owned store from
  that revision; nested persistence stages both parts for one final commit.
  Callback failure restores memory without a remote write; a conflicting or
  uncertain commit requires cold reconciliation, never a compensating overwrite.
  This is private campaign metadata, not public release/runtime Registry authority.
  The Community envelope is now `chummer.hub.community-primary/v2`, so old writers
  reject rather than silently discard the added metadata. No production Community
  primary has been activated. Existing v1 snapshots require explicit migration;
  there is no automatic v1 conversion or local-file import.
  Campaign workspace, organizer, open-run and movement operations now retain one
  current Community scope across their read/admission/write sequence. A stale
  principal mapping cannot seed or mutate the reassigned account. In primary mode,
  open-run closeout stages its resolution approval, world tick, player-safe news
  and closed listing for one commit. A validation failure restores memory; a
  conflicting or uncertain commit requires cold readback without replay. Campaign
  construction requires an explicit support dependency instead of inventing a
  temporary local support store. These changes do not migrate every Campaign
  collaborator or establish a distributed read lease.
  This slice is **not registered for production**: remaining Community consumers,
  other auxiliary stores and historical erasure still need conversion.
- Support cases, crash incidents/clusters/work items and their indexes now have
  an explicit primary registration. Every outer case/crash/Campaign support read
  refreshes the support snapshot; nested operations retain pending changes.
  Crash intake and its case/index projection commit together; the outer identical
  persistence call does not create a second revision. Conflicting or uncertain
  snapshot writes disable the instance until cold reconciliation. Missing/corrupt
  primary state never falls back to a local file or silently restarts empty.
  Actual attachment bytes use bounded immutable revision-1 streams in the same
  table. All inputs are checked before a batch starts; case references are saved
  only after successful blob storage. An interrupted blob/batch can leave inert
  orphan bytes, not a downloadable partial case. Downloads check current reporter
  access and case attachment membership in one synchronous scope, then validate
  immutable blob identity and metadata. Extension-based download MIME is retained.
  This is not a distributed read lease or an email/reward outbox transaction.
  Historical support/attachment erasure remains unsupported and now rejects at
  the beginning of account erasure, before journal or other account side effects.
  No runtime configuration is changed by this registration.

Identity configuration, for an isolated migration environment only:

```text
CHUMMER_IDENTITY_STORAGE_PROVIDER=teable
CHUMMER_TEABLE_ORIGIN=https://app.teable.ai/
CHUMMER_TEABLE_TABLE_ID=<dedicated primary table>
CHUMMER_TEABLE_TOKEN_FILE=<absolute private mounted token file>
```

Use a dedicated base-scoped runtime credential, not EA's broader credential.
The file must be a private, owned regular file, not a symlink; HTTPS is mandatory
and redirects are disabled. Default local mode is unchanged. No automatic local
import occurs when primary mode is enabled.

Support cases and attachments share one explicit primary configuration:

```text
CHUMMER_SUPPORT_STORAGE_PROVIDER=teable
CHUMMER_SUPPORT_TEABLE_TABLE_ID=<dedicated support primary table>
CHUMMER_SUPPORT_TEABLE_TOKEN_FILE=<absolute private mounted token file>
```

The attachment service must use the same SupportStore instance. A mixed local
attachment/primary case configuration rejects rather than creating local blobs.

Origin uses a separate table/token registration:

```text
CHUMMER_ORIGIN_CHAPTER_STORAGE_PROVIDER=teable
CHUMMER_ORIGIN_TEABLE_TABLE_ID=<dedicated chapter table>
CHUMMER_ORIGIN_TEABLE_TOKEN_FILE=<absolute private mounted token file>
```

Private first-party documents have their own explicit registration:

```text
CHUMMER_ORIGIN_DOCUMENT_STORAGE_PROVIDER=teable
CHUMMER_ORIGIN_DOCUMENT_TEABLE_TABLE_ID=<dedicated private document table>
CHUMMER_ORIGIN_DOCUMENT_TEABLE_TOKEN_FILE=<absolute private mounted token file>
```

This does not import or read a legacy local document directory. Existing owner
and global capacity settings also apply to inert remote reservations. Document
deletion remains rejected until historical/orphan erasure is safe. The account
auxiliary-erasure entry point checks this limitation before its first mutation,
rather than deleting other stores and claiming the document history is gone.

Linked runner snapshots use a distinct explicit registration:

```text
CHUMMER_INSTALL_LINKED_WORKSPACE_STORAGE_PROVIDER=teable
CHUMMER_INSTALL_LINKED_WORKSPACE_TEABLE_TABLE_ID=<dedicated private workspace table>
CHUMMER_INSTALL_LINKED_WORKSPACE_TEABLE_TOKEN_FILE=<absolute private mounted token file>
```

This is transport custody, not new Core rule or continuation-application authority.
No legacy file import or distributed read fence is implied. Scope entry must be
synchronous and cannot cross an `await`. Historical workspace erasure remains
blocked and is checked before any auxiliary-account deletion takes place.

Authoring usage and reservations use distinct explicit registrations:

```text
CHUMMER_MYFIRSTBOOK_USAGE_STORAGE_PROVIDER=teable
CHUMMER_MYFIRSTBOOK_USAGE_TEABLE_TABLE_ID=<dedicated private usage table>
CHUMMER_MYFIRSTBOOK_USAGE_TEABLE_TOKEN_FILE=<absolute private mounted token file>
CHUMMER_ORIGIN_PROVIDER_RESERVATION_STORAGE_PROVIDER=teable
CHUMMER_ORIGIN_PROVIDER_RESERVATION_TEABLE_TABLE_ID=<dedicated private reservation table>
CHUMMER_ORIGIN_PROVIDER_RESERVATION_TEABLE_TOKEN_FILE=<absolute private mounted token file>
```

These preserve the existing case-insensitive billing-user and monthly-window
semantics, not the separate opaque subject identity rules. Historical erasure is
preflighted before auxiliary mutations.

The membership input to those quotas has its own registration:

```text
CHUMMER_BILLING_MEMBERSHIP_STORAGE_PROVIDER=teable
CHUMMER_BILLING_MEMBERSHIP_TEABLE_TABLE_ID=<dedicated private membership table>
CHUMMER_BILLING_MEMBERSHIP_TEABLE_TOKEN_FILE=<absolute private mounted token file>
```

The existing provider sync secret and status configuration remain required at
their original boundaries. Neither secret is copied into membership rows. No
legacy billing file is imported automatically, and historical membership erasure
is rejected before any auxiliary-account deletion begins.

Horizon usage and request receipts have separate registrations:

```text
CHUMMER_HORIZON_ARTIFACT_USAGE_STORAGE_PROVIDER=teable
CHUMMER_HORIZON_ARTIFACT_USAGE_TEABLE_TABLE_ID=<dedicated private usage table>
CHUMMER_HORIZON_ARTIFACT_USAGE_TEABLE_TOKEN_FILE=<absolute private mounted token file>
CHUMMER_HORIZON_REQUEST_RECEIPT_STORAGE_PROVIDER=teable
CHUMMER_HORIZON_REQUEST_RECEIPT_TEABLE_TABLE_ID=<dedicated private receipt table>
CHUMMER_HORIZON_REQUEST_RECEIPT_TEABLE_TOKEN_FILE=<absolute private mounted token file>
```

These are stored usage and request records, not provider outputs or publication
authority. Historical deletion remains rejected before auxiliary erasure starts.
The existing compose-only/provider-disabled boundaries are unchanged.
New charged receipts are part of the authoritative usage row; receipt queries
must go through `HorizonArtifactRequestService`, not the standalone legacy store.
Existing counts with no receipt retain that lack of historical attribution; no
receipt is invented for them. The bounded usage JSON depth permits the nested
receipt while retaining its byte cap and exact owner/window/count validation.

API account/key custody uses distinct explicit registrations:

```text
ASPNETCORE_ENVIRONMENT=Production
CHUMMER_INSTALL_LINKING_STORAGE_PROVIDER=teable
CHUMMER_INSTALL_LINKING_STORE_PATH=<absolute disposable local mirror path>
CHUMMER_INSTALL_LINKING_TEABLE_TABLE_ID=<dedicated account snapshot table>
CHUMMER_INSTALL_LINKING_TEABLE_TOKEN_FILE=<absolute private mounted token file>
CHUMMER_DATA_PROTECTION_KEY_PROTECTION_MODE=teable_primary
CHUMMER_DATA_PROTECTION_TEABLE_TABLE_ID=<dedicated private key table>
CHUMMER_DATA_PROTECTION_TEABLE_TOKEN_FILE=<absolute private mounted token file>
```

The actual Data Protection keys live in the private table without the old
certificate wrapping, as explicitly requested. They remain sensitive material;
neither the table nor its credentials may be public. Do not carry over competing
PostgreSQL connection-string or certificate settings. An unreadable encrypted
key history fails startup validation; it is not replaced with new keys. Rook's
PostgreSQL read-fence semantics and the PostgreSQL-specific runtime-role endpoint
are **not** claimed by this backend. That deployment/readback distinction remains
to be resolved before a public cutover.

All primary modes remain deployment work in progress, not switches to enable on
the public Hub yet. Origin history erasure also deliberately rejects until its
cleanup is implemented. No actual First Book execution was implied by a job test.

## Verified, deliberately bounded

Local Docker focused tests: 58 passed, followed by 11 Identity tests after adding
a competing email-completion case. Three Docker-context contract tests passed.
The local diagnostic build uses the already cached Core package override and
SDK 10.0.111; this is not a new package seal, hosted result or deployment proof.

On 2026-09-23, three isolated read-only C# processes used the real Teable API and
synthetic accounts: issue, cold restore plus revoke/role change, then cold verify.
All passed without local account data files. Tokens travelled only in private
stdin/stdout captured in memory. No email or book generation was invoked.
This proves the Identity adapter, not restoration of the complete Hub host.

Origin follow-up: 28 focused chapter/worker tests passed, followed by 11 primary-
storage tests including private-token DI configuration. Three further isolated
processes passed a real-Teable synthetic chapter create/dispatch-fence, cold
reconciliation/completion/reader acceptance, and cold text/owner/book verification
at 2026-09-23 05:53–05:54 UTC. No local book files or provider call. The probe links
the actual API project; it is not a public HTTP/deployment or full book export test.

The Community slice passed 31 focused primary-storage tests (9 Community,
11 Identity, 11 Origin). The first run had one randomized test-fixture ordering
error in the hostile principal-ownership case; the corrected test explicitly
assigns the other row's subject. The product rejects that ambiguity. Community's
proof is against the simulated transport, not an actual-account/live migration.
The 47 existing affected account-capture, identity-link, group-invite, ledger,
experience and account-erasure regressions also pass. Both bounded runs built
the affected API and test assembly without compiler warnings/errors.

API activation follow-up: 69 focused tests passed for the production Teable
registration, cold key/account restoration, grant revocation, stale mirror
rejection, remote key outages, encrypted-history rejection, mixed configuration
rejection, transport revisions, existing activation and PostgreSQL coordinator
regressions. The first test compilation found a non-constant optional test-host
parameter; it was corrected before execution. The terminal test replay reused
the compiled local assembly (`--no-build`); no hosted or live-deployment result
is implied. The actual production registrations were exercised with simulated
Teable transport. PostgreSQL remains the default and retains its status codes.

Document follow-up: 44 focused local Docker tests passed, including the existing
first-party document/controller and auxiliary-account-erasure regressions. New
cases cover cold byte-identical document/export restore without local files,
owner/subject/project isolation, capacity admission races, inert reservations,
lost export acknowledgement, competing exports, primary outage without local
fallback, hostile artifacts/catalogues and erasure preflight. The initial run
passed 42 and found one invalid-metadata exception-classification defect: a missing
owner digest reached an argument-null exception. It is now rejected as invalid
stored data before comparison. The successful follow-up includes an added test
proving erasure stops before unrelated auxiliary records are removed. API and test
assembly compiled without warnings/errors. These are simulated-transport tests,
not a live Teable or whole-host restore and not provider execution.

Linked workspace follow-up: the terminal local Docker run passed 98 focused
workspace-primary, Android bearer-proof and auxiliary-erasure tests. The earlier
179-case run passed 178, failing only the production DI fixture's unintended
PostgreSQL configuration; the fixture now selects the explicit primary backend.
The next run exposed a real error-mapping gap: `InvalidDataException` did not
map to 503 on rollback detection. That was corrected before the terminal pass.
Complete snapshots, account separation, owner-switch rollback rejection, same-
owner races, uncertain writes, old local-file preservation and erasure preflight
are covered. API/test builds have no compiler warnings/errors; the SDK workload
notice is not a new workload qualification. This is simulated transport, not
live account migration or whole-host reconstruction. A final 15-case workspace
run also passed after tightening every hostile-record assertion to require 503.

Authoring ledger follow-up: 88 focused tests passed across primary usage and
reservations, existing billing/controller and reservation-service cases, and
auxiliary-erasure preflight. The initial test compilation lacked the existing
`RepoPaths` helper in the bounded test group; it was included without changing
product logic. A further 30 tests passed after adding the stale-quota-read race,
rollback rejection and failed-local-persistence regressions, including the shared
revision transport tests. API and test builds have no compiler warnings/errors.
All remote data in this verification is synthetic, using simulated transport;
no provider generation, live Teable record or production configuration changed.

Membership follow-up: 92 focused tests passed across primary membership and
authoring ledgers, existing billing/controller behavior and auxiliary erasure.
Cases include combined cold membership/usage restoration, a second instance's
downgrade, rejection before I/O for bad sync credentials or plan/status inputs,
conflicts, uncertain commit readback, local-file isolation, custom status mapping
and incompatible policy, corrupt rows, failed-local-sync rollback, explicit DI
and erasure preflight. API/test compilation has no compiler warnings/errors.
This is simulated transport, not live customer migration or provider readback.

Horizon follow-up: 23 existing governed-render/capability/domain-bridge tests
passed. The focused primary-ledger, billing, reservation and erasure run passed
110 tests, including cold receipt/usage restore, competing last slots and batch
charges, lost acknowledgements, hostile rows, overflow rejection and deletion
preflight. After the original process handle was lost, the terminal result was
recovered with a bounded `--no-build --no-restore` test replay of the already
compiled assembly; no unchanged build or full suite was repeated. Tests use
synthetic simulated transport. No live data, provider, deployment or Play change.

Atomic charge follow-up: the existing 23 render-path tests passed, then 122
focused ledger/billing/reservation/erasure tests passed. Coverage includes one
charge/receipt commit, rejected commit, uncertain acknowledgement, competing
writers, cold owner-filtered reads, duplicate-charge rejection, hostile detached
counts, and local-file cold restore alongside legacy receipts. The first 120-test
run passed 118; two controller tests still read the standalone receipt store.
They now verify the shared request query service and retain their response/header
assertions. The analogous public landing reload test was adjusted but was not in
this bounded execution; two new local cold-restore cases exercise the new read
model. API and bounded test assembly compiled without warnings/errors. No live
Teable data, public deployment, provider dispatch or Play operation was performed.

Community projection follow-up: 58 focused tests passed for primary Community,
existing Teable user projections, canonical account capture, group invites,
ledger and user-experience behavior. New cases cover cold recognition readback,
remote public-consent withdrawal, nested pending snapshots, fresh operator rows,
Passport/Signal Deck notification counts and primary outages without cached
results. The initial run passed 56/58: two new summary tests supplied a null
legacy installation dependency. The fixture now uses the supported unready
production activation/access path; no product fallback was weakened. API/test
builds have no compiler warnings/errors. Live Teable, provider and production
configuration remain unchanged; this is simulated remote verification.

Runtime credential preparation: the existing EA API token returned HTTP 403 from
the read-only `/api/access-token` metadata endpoint. It has not been deployed to
Hub. No existing BrowserAct profile is scoped to Teable; approval for a separate
local Teable profile and a dedicated base-scoped credential has been requested.
Do not reuse a GitHub/Play/provider profile or put the broad EA token in Hub.

Faction follow-up: 39 focused tests passed across the primary faction and
Community stores and existing faction onboarding/charter behavior. Cases cover
cold charter/allegiance/lore/action restoration without local files, current
moderation/consent, cooldown and capacity checks, competing last-action-point
writes, uncertain commit readback without replay, nested pending state and
outages. API/test builds completed without compiler warnings/errors after fixing
a missing namespace in the new test fixture. This uses simulated Teable transport,
not real account data or a production cutover. BrowserAct's current inventory was
checked read-only: none of its 23 profiles is scoped to Teable. New isolated
profile/login and restricted runtime-token setup still need explicit approval.

Sponsor observation follow-up: 44 focused tests passed for primary sponsor
state, existing participation input guards, Community, ledger and group behavior.
This includes cold intent/consent restoration, fresh Fleet status and recognition,
delayed reply versus revocation/lane/account changes, same-store nonblocking
observation, a competing final commit, wrong-lane rejection, outage after the
external read and no primary Fleet mutation/auto-activation. The existing local
auto-activation path is retained and checked with a simulated Fleet handler.
41 tests passed first; three focused commit/outage/local-compatibility cases were
then added and all 44 passed. API and test compilation is clean. No Teable or
Fleet network calls, credential changes, deployment or Play operations occurred.

Campaign artifact follow-up: 96 focused tests passed across the new primary
artifact transaction, existing Campaign guardrails, Community, faction and sponsor
storage. Cases cover one-commit aftermath/metadata restore without local files,
fresh metadata on an existing bridge, callback rollback, competing and uncertain
commits, malformed/incomplete/v1 snapshots and outage without local fallback.
The existing local-file compatibility and campaign guardrail tests remain green.
The preceding process's terminal result was unavailable after handoff; this result
comes from a network-disabled `--no-build --no-restore` replay of its compiled
assembly, not a new build or hosted qualification. All remote data is synthetic.
No actual account migration, runtime activation, provider or Play operation.

Support follow-up: 91 focused local Docker tests pass across new primary case,
crash and attachment storage, existing support/upload/account-erasure tests and
Campaign regressions. Coverage includes complete cold case/attachment restoration,
reporter reassignment, current download access, one-commit crash idempotency,
conflicts, uncertain case/blob writes, nested reads, malformed snapshots, orphan
non-disclosure, immutable blob checks, MIME safety, outage isolation and erasure
preflight. The initial 89-case run passed 88; the remaining new assertion compared
timeline dictionary object identities rather than serialized content. The corrected
test checks the whole case's serialized content; two focused attachment tests were
added. API/test builds completed without compiler warnings/errors. Tests use
synthetic simulated transport with networking disabled, not real accounts or a
whole-host restore. No provider, email, credential, deployment or Play action.

Campaign spine follow-up: 109 focused tests pass across primary Campaign,
artifact, support, Community and faction storage and existing Campaign guardrail,
movement and adoption behavior. Nine new cases cover cold restore without local
files, atomic closeout, conflict/lost-acknowledgement recovery, invalid-input
rollback, revoked membership, reassigned principal, movement receipts and outage
isolation. The terminal result was recovered with a network-disabled local Docker
`--no-build --no-restore` run of the current compiled assembly after the previous
process handle was lost. No new package seal or hosted qualification is claimed.
All remote data is synthetic simulated transport; no accounts were transferred,
no production mode was enabled, and no provider or Play action occurred.

## Remaining before production cutover

1. Finish Community consumer/DI conversion and remaining document/artifact
   stores. Origin jobs, private first-party documents, linked runner snapshots,
   MyFirstBook usage, Origin credit reservations, billing membership, Horizon
   usage and request receipts have primary implementations with atomic new
   charge/receipt storage. Support cases/crashes and attachment bytes now have
   primary implementations too, but historical/orphan erasure remains open.
   Publication-index/provider-output artifacts and other
   auxiliary stores still need custody review. The isolated Community slice is
   not a complete activation. Faction onboarding's cached state is now removed;
   sponsor observations are freshly rebound after their GET, but the legacy
   Fleet mutation paths still carry mutable state over external awaits. Those
   paths remain explicitly blocked in primary mode until durable operation
   fences and uncertain-outcome reconciliation exist. Campaign recap/replay
   metadata now co-commits with aftermath, and CampaignSpine operations use fresh
   scopes with atomic open-run closeout; other Campaign collaborators and auxiliary
   consumers still need conversion. This is not whole-Campaign activation.
2. Complete the runtime readiness/deployment readback for the new primary backend;
   do not reuse a PostgreSQL least-privilege proof as a Teable proof. API primary
   registration and key custody are implemented but not activated publicly.
3. Erasure of historical private snapshots and orphan chunks. Identity account
   erasure currently rejects Teable mode rather than claiming a false deletion.
4. Restricted production credentials and complete configuration/secret custody.
   The bootstrap credential needs independent recovery outside its own base.
5. A cold reconstruction of the complete fresh Hub and owner/auth/book checks,
   followed by controlled cutover. Do not deploy only the Identity half.

Append-only hashes are not protection from a privileged table administrator.
This store is not a distributed read-lock/lease provider and does not authorize
Rook or guarantee automatic failover or zero data loss.
