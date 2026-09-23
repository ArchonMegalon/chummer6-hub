# Teable primary migration — in progress

The user's 2026-09-23 decision makes Teable the primary working store for the
fresh Hub account and Origin book/job state. This is not a backup/projection.
Production has **not** been cut over. The original encrypted Docker volume is
preserved; none of its unreadable records were decrypted or silently imported.

### Live restricted-access follow-up (2026-09-23)

The owner approved and two separate project-restricted runtime credentials were
created (Identity/Hub, record read/create plus field read, expiry 2026-12-22).
Existing broad operator credentials are unchanged and are not mounted in either
service. Exact selected credential/configuration bytes and file references were
backed up to the independent private EA recovery table and read back. Both new
tokens reject access to that recovery table, updates, deletes and table inventory.
Dedicated Identity/Hub revision tables passed schema, synthetic append/read and
duplicate-key rejection checks. Grants are project-level, not per-table isolation.

An isolated local Production-mode smoke reused the preparation images below.
Identity became healthy; Hub health passed and deep readiness accepted remote
Data Protection and install-linking authority. Whole-Hub readiness remained false:
the preparation image lacks release/deployment authority and public canon assets.
Startup also exposed unscoped legacy Community reads in the Black Ledger news
worker and Important Work reconciler; the latter has a separate reconcile switch
not disabled by the current Compose file. These are live integration findings,
not reasons to relax readiness or claim a completed migration.

The temporary containers/network were removed afterward, retaining all new
private configuration, state roots and remote bytes. Existing services, original
volumes and Cloudflare were untouched. No real account/book migration, authoring
provider dispatch, signed build or Play upload occurred. Authenticated cold
account/book restoration, current public assets and actual First Book narration
remain open.

### Startup correction (2026-09-23)

The disabled Important Work reconciler now returns without reading Community
state, and its explicit record/dashboard operations use current primary scopes.
The news dispatch worker exits before reading recipients or seeding catch-up
receipts when email delivery is disabled. The isolated Compose preparation now
explicitly disables reconciliation, autosync and news email as well as projection.
All 34 focused Community/Important Work tests and 14 Compose checks pass locally.
Coverage includes cold reads, competing writes, outages and disabled-worker
non-execution. This does not enable primary news delivery or establish deployment,
provider generation, public readiness or Play publication.

The corrected local image also includes the tracked public canon runtime files.
Login/health and the isolated worker access boundaries passed. A real HTTP smoke
issued a short-lived synthetic session, created its private Hub profile, recreated
both containers with empty local state roots, and restored the exact profile and
session from Teable. Session revocation was observed afterward. This is bounded
account recovery, not a whole-Hub/provider/book migration.

The Android device-link approval route passed, but its subsequent signed exchange
exceeded the client's 35-second wait. A separate primary read proved the callback
and grant had committed. The owned synthetic grant was explicitly revoked; no
paid operation was involved. Inspection and a failing regression found 174 remote
GETs during a single bootstrap because every dictionary lookup re-evaluated the
store activation. The v2 exchange now uses a synchronous operation-local view
under the same store gate, retaining explicit readiness checks, nonce admission,
mutation CAS and a final primary check before releasing its reply. The focused
regression measures 44 GETs (42 when final readback fails); 101 existing/focused
checks plus two final outage/recovery cases pass locally. A committed result after
an outage is recovered with the original operation identity and grant, not newly
issued. The new optimized source still needs a live HTTP retest; no latency or
deployment claim is inferred from the simulated transport test.

The subsequent image's HTTP check failed earlier, with 503 at device approval:
startup had retained an unavailable install-linking activation. The five-second
readiness check downloaded the current protected envelope twice. A new regression
confirmed five remote reads (schema, head/chunk, head/chunk). The Teable adapter
now returns its schema-verified envelope to the coordinator for the exact bound-head
comparison: three reads, no caching or skipped validation. The existing deadline,
PostgreSQL readiness path, mutation CAS and fresh per-operation checks remain.
114 focused transport/activation/signed-request tests and 31 existing coordinator/
activation compatibility tests pass locally. Bootstrap now measures 32 GETs. The live
device-link route still requires testing against this changed image; neither the
previous health response nor these tests establish real narration or publication.

The single-envelope image passed live browser approval (200, 23.28 seconds),
bootstrap (200, 18.51 seconds) and signed grant status (200, 26.44 seconds), but
private chapter lookup exceeded 35 seconds. The signed cleanup response was also
lost and requires read-only reconciliation; the synthetic Identity session was
revoked. No chapter or provider operation was created. A separate cold diagnostic
also encountered a 15-second key-store read timeout, so network availability is
not inferred from the earlier passing requests.

The affected v2 principal resolution, replay admission and revocation now use the
same synchronous operation-local store pattern as bootstrap, with fresh final
authority checks. One signed admission sequence falls from 73 remote GETs to 43;
no cross-request cache or weakened signature/owner/replay admission was added.
134 focused local tests pass, followed by two expanded recovery cases proving
that committed nonces cannot replay and committed revocation survives a lost
final response and cold restore. Live retesting of this new source is still due.

The live follow-up also located the same repeated getter pattern in browser
approval. That method now captures one synchronous operation-local view and
performs a final current-authority check. 116 affected callback/activation/v2
tests pass, including an explicit approval read bound. The live failure at this
stage was a primary read becoming unavailable (500); separate Identity cleanup
also timed out at a remote append and requires cold readback before another write.
No transient failure was treated as permission to replay or widen timeouts.

Readiness now overlaps the independent read-only schema and current-envelope
observations within the same five-second deadline. Both must succeed before the
envelope is returned, and a successful envelope is disposed if schema validation
fails. A focused barrier test proves overlap and rejects invalid schema; 42
affected transport/activation/coordinator cases pass. This reduces serial network
latency, not the freshness or safety requirements, and is not yet live completion.

### Completed bounded HTTP recovery — 2026-09-23 15:35 UTC

Functional source `9b6732d2d` ran as local image
`sha256:dca394bb027d65c591e7beb6a22773f91ee04a60f4c56f989c6cc90ee0f3129c`.
The same previously approved synthetic operation resumed successfully (200,
10.44s), without another account/approval. Signed status returned 200 (13.89s)
and the private nonexistent-chapter lookup returned the expected 404 (15.91s).
After restarting the Hub, the same grant returned status 200 (12.00s) and the
same lookup returned 404 (15.00s). Explicit revocation returned 200 (18.26s),
followed by a rejected signed status request (401, 2.49s). Generated temporary
test credentials were removed only after that verified rejection.

Earlier synthetic session revocations with lost responses were independently
read back as inactive after cold Identity restart, without replaying the writes.
This establishes bounded live install/account recovery and private route admission,
not actual chapter generation, reading/adoption, complete host recovery, public
cutover or Play delivery. Latency remains visible; no network SLO is claimed.

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
  The Community envelope is now `chummer.hub.community-primary/v3`: v2 added
  campaign metadata; v3 also retains invitation failure windows. Old writers
  must reject rather than silently discard either field. No production Community
  primary has been activated. Existing v1/v2 snapshots require explicit migration;
  there is no automatic older-schema conversion or local-file import.
  Campaign workspace, organizer, open-run and movement operations now retain one
  current Community scope across their read/admission/write sequence. A stale
  principal mapping cannot seed or mutate the reassigned account. In primary mode,
  open-run closeout stages its resolution approval, world tick, player-safe news
  and closed listing for one commit. A validation failure restores memory; a
  conflicting or uncertain commit requires cold readback without replay. Campaign
  construction requires an explicit support dependency instead of inventing a
  temporary local support store. These changes do not migrate every Campaign
  collaborator or establish a distributed read lease.
  Campaign collaboration now refreshes reads, campaign/invite creation, redemption,
  membership authority and runsite operations. Primary transactions roll back the
  complete in-memory snapshot and commit membership, invite consumption and replay
  response together. Failed invitation attempts persist across instances/restarts;
  successful new redemption clears that budget in the membership commit. An
  already-committed redemption replay does not reset the primary failure budget.
  Recoverable Data Protection keys preserve invite-secret replay; constructors
  using the known ephemeral provider reject primary mode. The deployment still
  needs the configured remote-key readiness check, not merely a non-ephemeral type.
  The external Core edit path remains unavailable in primary mode until a durable
  operation fence/reconciliation spans Core execution and the Community commit.
  This is not whole-Campaign activation or general delegated-edit authority.
  This slice is **not deployed in production**: remaining Community consumers,
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

### Erasure admission during partial migration

Account erasure now preflights the actual Support, Community and auxiliary store
implementations before starting its journal or deleting Hosted Build workspaces.
Auxiliary preflight includes chapter jobs and install-linking, not only usage,
documents and workspace snapshots. Direct entry points retain their own guards.
The install-linking Teable adapter cannot report successful erasure while older
protected snapshots and their readable keys remain. Backend naming alone cannot
turn that append-only adapter into a history-erasing store.

Four focused regression cases reproduced destructive partial erasure or a false
success before the correction. The corrected local API/test build passes 72
focused tests, including those four and two backend-label cases. Tests use
simulated Teable transport with networking disabled; they verify unchanged local
bytes, remote heads, grants, support cases and no journal/remote-erasure dispatch
on rejected admission. No real records were erased and no production service was
changed. This closes the late-admission defect, **not historical erasure itself**.
Historical cleanup, cross-service Identity readiness and the full deployment
restore remain unfinished; these guards are not a cutover authorization.

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

Configuration recovery follow-up: `Chummer.Teable.Recovery` and the shared
`TeableRecoveryBundleStore` now capture an explicit flat allowlist of actual
configuration/secret file bytes into a private revision stream. No directory scan,
service execution, secret output or existing-target overwrite is supported.
Restore binds an exact inspected receipt, validates all names/lengths/digests,
writes owner-only files into a private staging directory, reads them back and
then moves that directory to a new target. Identical captures reuse their head;
concurrent changes reject and uncertain captures require readback without replay.
Bootstrap Teable access must be independently recoverable outside this host/base.
The usage and limitations are in `Chummer.Teable.Recovery/README.md`.

62 focused local tests pass, including 26 recovery cases and existing transport,
Identity and secure-file tests. The first 59-case run passed with platform
warnings; those were fixed. A later FIFO timeout test was incorrectly synchronous
and rejected by xUnit (61/62); the corrected asynchronous test and final build
pass without compiler warnings/errors. The CLI also builds cleanly and its two
isolated negative invocations return only usage or a bounded error, never a stack
trace or credential material. All verification is network-disabled and synthetic.
No real configuration/secret files were captured or restored. This tool does not
prove complete file selection, image availability, working credentials, whole-Hub
restoration or production cutover, and it does not purge historical secret copies.

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

Campaign collaboration follow-up: 124 focused local Docker tests pass, including
12 new primary cases and the existing collaboration suite. Coverage includes
independent remote-key providers, exact invitation replay after cold restore,
one-use races, lost-acknowledgement membership recovery, runsite visibility,
revocation/reassigned principals, rollback and persistent failure throttling.
Old v2 or missing/invalid admission state rejects. API/tests compile without
warnings/errors after correcting a new guard's parameter name. The first executable
run passed 119/120: its short-code fixture was malformed and never reached the
counter. The corrected fixture uses a valid-format wrong code and verifies each
persisted counter; four restore-rejection cases were also added. Simulated remote
transport only, network disabled. No live account migration, provider, key/credential
operation, deployment or Play change occurred.

### Live synthetic Community/support restoration — 2026-09-23

Three independent, read-only-filesystem Docker processes completed against the
existing explicitly synthetic Teable table. Source implementation:
`25dc0c002eb3fa870b799351a6c74930d897a335`; reused API assembly SHA-256:
`afb7fbf99ca17a4f9ce03d92f2dcad16bb0046ba413dc02a50e7e452a596430b`.
The small diagnostic executable was built locally against that existing assembly;
this was not another Hub build, package seal or release qualification.

- `create`, 09:28:49 UTC: synthetic accounts, campaign/dossier, protected invite,
  support case and a chunk-spanning attachment were stored in the test table.
- `restore-and-join`, 09:29:46 UTC: a fresh process read the existing accounts,
  restored the identical invitation secrets through the remote keyring, redeemed
  once, issued/revoked a second invite and read the exact attachment bytes.
- `cold-verify`, 09:30:53 UTC: a third process restored membership and the exact
  prior redemption without consuming again, observed the invite revocation, and
  rejected foreign account access to both case and attachment. Attachment SHA-256
  matched and no local account/attachment directory was created.

Only synthetic data was written. The existing operator credential stayed in
stdin/process memory for this bounded diagnostic; it was not installed in Hub or
stored in an image, argument list or credential file. A restricted production
credential remains unprovisioned. No email/authoring provider, production service,
Cloudflare, signing or Play action occurred. All three containers exited and were
removed. This does not prove complete deployment/configuration recovery, historical
erasure, a physical host failover or migration of real users. The driver refuses
to repeat its creation phase over an existing synthetic Community snapshot.

## Remaining before production cutover

1. Finish Community consumer conversion and remaining document/artifact
   stores. Origin jobs, private first-party documents, linked runner snapshots,
   MyFirstBook usage, Origin credit reservations, billing membership, Horizon
   usage and request receipts have primary implementations with atomic new
   charge/receipt storage. Support cases/crashes and attachment bytes now have
   primary implementations too, but historical/orphan erasure remains open.
   Private Origin publication indexes and artifact bytes now have primary custody;
   other auxiliary stores still need review. The isolated Community slice is
   not a complete activation. Faction onboarding's cached state is now removed;
   sponsor observations are freshly rebound after their GET, but the legacy
   Fleet mutation paths still carry mutable state over external awaits. Those
   paths remain explicitly blocked in primary mode until durable operation
   fences and uncertain-outcome reconciliation exist. Campaign recap/replay
   metadata now co-commits with aftermath, and CampaignSpine operations use fresh
   scopes with atomic open-run closeout. Collaboration's invitation/membership and
   runsite paths now use current primary state, but external Core editing still
   requires a cross-store operation fence. Other collaborators and auxiliary
   consumers still need conversion. This is not whole-Campaign activation.
2. Complete the runtime readiness/deployment readback for the new primary backend;
   do not reuse a PostgreSQL least-privilege proof as a Teable proof. API primary
   registration and key custody are implemented but not activated publicly.
3. Erasure of historical private snapshots and orphan chunks. Identity account
   erasure currently rejects Teable mode rather than claiming a false deletion.
4. Restricted production credentials and complete actual configuration/secret custody.
   The selected-file recovery tool is implemented and tested; inventorying and
   capturing the real complete deployment and cold-starting it are still required.
   The bootstrap credential needs independent recovery outside its own base.
5. A cold reconstruction of the complete fresh Hub and owner/auth/book checks,
   followed by controlled cutover. Do not deploy only the Identity half.

Append-only hashes are not protection from a privileged table administrator.
This store is not a distributed read-lock/lease provider and does not authorize
Rook or guarantee automatic failover or zero data loss.

## Private publication and export custody — 2026-09-23

`OriginDossierPublicationService` now has an explicit Teable primary mode for
its private account publication index and the actual artifact bytes. This is not
public Registry publication authority or a new provider-generation permission.
The existing manuscript, consent, canon, cover, packaging and provider-receipt
validators apply to the restored bytes unchanged. Drafts do not become approved
books merely by moving to Teable.

```text
CHUMMER_ORIGIN_PUBLICATION_STORAGE_PROVIDER=teable
CHUMMER_ORIGIN_PUBLICATION_TEABLE_TABLE_ID=<dedicated private publication table>
CHUMMER_ORIGIN_PUBLICATION_TEABLE_TOKEN_FILE=<private mounted runtime token>
CHUMMER_ORIGIN_PUBLICATION_IMPORT_ROOT=<optional absolute private staging root>
```

Fresh synchronous scopes read the current primary index. Artifact references bind
the exact owner/project and content digest. Immutable revision-1 blobs contain
the owner binding and complete bytes; missing, replaced or corrupt blobs and
remote outages fail without local fallback. API downloads copy bytes before
scope cleanup and retain existing MIME/range behavior. Portrait, voice and scene
selections persist through the same index compare-and-exchange. Foreign account
requests still cannot download or change the owner's publication.

Operator imports are opt-in, Linux x64 only, beneath
`<import-root>/<owner-project-hash>/`. Directories and regular files must be
private and owned; symlinks, unsafe permissions and paths outside that namespace
reject. No legacy index is automatically imported. Artifact bytes are committed
before the index, so a failed admission can leave private orphan blobs. Historical
and orphan erasure is not implemented: account erasure rejects before auxiliary
side effects rather than claiming those bytes were removed.

Limits: 64 MiB per artifact, 128 MiB cached bytes per outer operation, and the
shared bounded index (4 MiB, at most 2048 entries). Nested scopes retain borrowed
bytes until the outer scope exits, then clear them. Content stream names hash
the full owner/content identity to fit the transport's 128-character limit.

Verification: 83 focused tests passed in keyless local Docker with networking
disabled, including primary cold restore, foreign ownership, stale concurrent
writes, uncertain commits, corrupt/missing/replaced bytes, nested scopes, private
staging, current owner changes and early erasure rejection. A full existing
publication fixture was imported, all its local files removed, and its validated
book/cover downloads and changed selections restored through fresh services.
This fixture is synthetic test data, not actual FirstBook/provider output.
The run also includes existing publication and auxiliary-erasure regressions;
the API/test build emitted no compiler warnings or errors.

The first run exposed an overlong stream key; the follow-up fixed that and the
nested cache lifetime. Three negative assertions initially used the wrong common
exception base; they now check the actual exact failure types. No failed run is
counted as passing. This is simulated-transport verification, not a live primary
cutover, complete host reconstruction, package reseal or Play delivery.

## Explicit Community runtime registration — 2026-09-23

The existing primary CommunityStore is now wired into the normal account-service
registration instead of requiring a manually constructed store. Configuration is
explicit and independent of the legacy Teable user-projection/export credential:

```text
CHUMMER_COMMUNITY_STORAGE_PROVIDER=teable
CHUMMER_COMMUNITY_TEABLE_TABLE_ID=<dedicated private Community table>
CHUMMER_COMMUNITY_TEABLE_TOKEN_FILE=<absolute private mounted token file>
CHUMMER_TEABLE_ORIGIN=https://app.teable.ai/
```

The DI container owns a separately keyed primary transport. Resolving an account
service loads and validates current Community state before returning it. Missing
table/token, unknown provider, malformed primary state or an outage rejects rather
than falling back to a local file or a broader ambient API key. Local mode retains
its existing snapshot and does not construct a remote transport.

90 focused local Docker tests pass, including seven new registration cases,
fresh service-container account restoration, startup rejection and existing
Community, billing, authoring, support and erasure regressions. The API/test build
is clean. The first run was 89/90: a new assertion confused the old projection's
enabled flag with its configured state; the corrected test verifies that no
external projection credentials/destination were supplied. The legacy projection
settings and defaults are unchanged and remain separate from primary storage.
Tests substitute only the keyed transport with synthetic in-memory HTTP; no real
Teable credential, provider call or production activation is implied.

This closes the registration gap, not all Community consumer work. In particular,
optional notification/external-work consumers still
need explicit scope/transaction migration; no full-Hub cutover is authorized by
this test. Historical erasure and complete deployment recovery remain open.

## Play session account authority — 2026-09-23

The existing session/invite/exchange/grant service now enters fresh synchronous
Community scopes. Its constructor no longer requires a legacy file gate. Current
membership, revocation and time high-water state restore remotely; only secret
hashes are persisted, and primary mode never reads or writes a local snapshot.
The primary writer cannot be replaced by a custom persistence implementation.

A conflicting or uncertain primary commit fences the instance until cold
reconciliation. Failure returns no credential, restores only the in-memory
candidate and never overwrites remote authority, retries redemption or restores
a consumed secret. Existing local-file rollback behavior is preserved.

This is storage compatibility, **not Play API activation**. The transport remains
limited to its local single-writer Testing harness. Startup, runtime policy and
the process lease reject attempted primary activation; a disabled feature creates
no lease file. A local OS file lock cannot establish exclusive remote ownership.
Crash-recoverable response delivery, browser proof and production admission are
not claimed by this change.

The new regressions reproduced ten failures before the patch (one disabled case
already passed). The corrected keyless local Docker run passed 80/80 focused
service, endpoint, Community and revision-transport tests, with clean API/test
compilation. Cases include cold restoration, current membership/revocation,
clock rollback, competing invite/exchange consumers, uncertain commits, no-replay,
outage rejection and legacy local rollback/endpoint behavior. Networking was
disabled; transport and account data were synthetic. No live account migration,
credential issuance, production service, provider activation or Play upload ran.

## Account participation receipts and dispatch fencing — 2026-09-23

Account sections call ParticipationOperatorNotificationService to read activity
receipts. That path now reads fresh Community primary state rather than the old
local gate; cold services restore the same private receipt metadata without
creating local files. Dispatch admission verifies current account ownership and
persists its existing pending receipt before making the EA request. Competing
instances must win that revision commit before sending. No synchronous Community
scope spans the HTTP wait.

Primary pending/unknown/legacy failed-delivery receipts do not automatically
retry. Suppressed receipts may still proceed after missing configuration is fixed,
because suppression never dispatched. A provider failure produces
`delivery_unknown`, not an assertion that nothing was sent. Provider error bodies
are not copied into primary account receipts or logs. Unknown attempts continue
to count toward the existing per-user cap.

Finalization re-reads the current receipt and account and compares detached
fingerprints. Removed/rebound/changed state rejects instead of being recreated
or overwritten. Persistence is outside the provider-error catch: an uncertain
final write cannot cause a second failure-state write or another send. A crash
after admission may leave a pending receipt requiring manual reconciliation;
this is at-most-one automatic dispatch admission, not exactly-once delivery or
proof of an operator receiving a message. Existing local retry policy remains.

13 new regressions failed before the change. The first patched run passed 43/45;
two tests expected HttpRequestException where the transport deliberately reports
an uncertain write as IOException. Those exact assertions were corrected.
The final keyless, network-isolated Docker run passed 112/112 focused primary,
legacy notification, Community, billing and canonical-account tests, with clean
API/test compilation. It includes duplicate/concurrent admission, claim/final
commit uncertainty, cold restore, outage and delayed ownership/removal cases.
Only synthetic HTTP transport was used. No EA service was started, no real
notification was sent, and no runtime configuration, browser session or Play
artifact changed. Full Hub migration and remaining optional consumers stay open.

## Optional Origin allowance during primary failure — 2026-09-23

The account-page allowance projection now returns unavailable for bounded primary
transport, deadline, schema and JSON failures. Previously those failures escaped
the optional projection and aborted the account page. Strict allowance reads and
consumption still propagate the actual failure; no cache, free-tier allowance or
zeroed usage replaces unreadable authority. Once remote state is readable, a
fresh service restores the consumed allowance unchanged.

Account root and participation views now label missing membership as unavailable,
with a Check membership action, instead of implying a Free plan/one-book allowance.
The existing known Free and Supporter displays remain unchanged.

91 focused local Docker tests pass, including seven new projection/route cases,
existing membership/authoring and billing checks and affected account routes.
The five initial storage-failure regressions reproduced the defect before the
patch. The intermediate run passed 86/91 because new strict-operation assertions
incorrectly assumed ledger failures permanently fence an instance; each outer
read actually reconciles afresh. Corrected assertions verify the real failure
types and maintain the injected timeout for each attempted operation. No primary
behavior was weakened to satisfy them. API/test compilation is clean. These are
synthetic, network-isolated checks, not rendered-browser or production evidence.

Earlier migration commits through `cfc710028` were synchronized to the existing
`feat/origin-chapter-jobs-20260922` development branch and remotely confirmed.
That is source backup, not a main merge, package seal, Hub cutover or Play release.

## Signed Android chapter access with primary storage — 2026-09-23

The signed Android chapter controller now handles primary transport/deadline
failures as a private 503 response with same-request reconciliation guidance.
It does not invent a missing job, successful acceptance or fresh generation.
Responses retain no-store headers and expose no backend exception detail.

The primary read introduced an authorization gap: a device grant revoked while
the read was in flight could still receive private prose or record reader
acceptance. The controller now resolves the same current install principal again
before returning the result. Reader acceptance also rechecks authorization after
loading/validating the exact stored text and before its idempotent return or write.
This closes the observed read-window race; it is not a distributed authorization
lease or a claim of atomicity between different stores.

Nine focused new cases initially produced eight failures and one passing cold
flow. After the correction, 112/112 signed-bearer, chapter, worker and primary
storage tests passed with clean API/test compilation in isolated local Docker.
The successful flow uses the real request-proof middleware, a reconstructed
install service, fresh primary chapter services, a single worker dispatch fence,
stored prose, explicit acceptance and cold readback without redispatch. Its install
store is the existing local test fixture and Teable transport is simulated; it
does not prove whole-Hub recovery, live provider generation or Android UI behavior.

Only synthetic data was used. No browser/credential action, production cutover,
provider call, signing or Play upload occurred. Restricted runtime credentials
and complete authenticated Hub restoration remain prerequisites for live narration.

## Combined account/private-book reconstruction — 2026-09-23

The account-route fixture now checks the account and private document controllers
together with explicit primary Community, support, membership, MyFirstBook usage,
Horizon usage/receipts and publication/document adapters. It opens the account,
consumes a synthetic allowance, previews/exports approved first-party notes, then
disposes the service container and deletes its isolated local test root. A new
container/root restores the same canonical user, consumed quota, document
projection and exact Markdown bytes through the normal controller calls. An
unauthenticated download rejects, repeat export retains the same document receipt,
and account/participation pages remain usable. No real provider is involved.

This is an existing-test extension, not new recovery infrastructure. The normal
bounded-context registrations are used with test-injected primary transports;
Identity admission and install-linking remain the local test fixtures. It does
not prove Program startup, hosted workers, public ingress, real login, complete
host recovery or production Teable credential provisioning.

The new reconstruction check passed immediately. Running its 39-test account
route class exposed one obsolete install fixture: it seeded a login subject into
the canonical user field, so the existing strict owner-unlink check rejected it.
The fixture now uses AccountService's actual canonical user ID. No runtime owner
check was loosened. The corrected API/test build and all 39 account-route tests
pass locally with network disabled. No production source, service or release
artifact changed in this follow-up.

## Local Docker preparation, not public cutover — 2026-09-23

`docker-compose.teable-primary-local.yml` is a standalone two-service preparation
using the existing Hub API and Identity application images, not an overlay for
the PostgreSQL/certificate public-edge stack. Do not combine those Compose files.
It has a separate project/network, no incumbent named volumes, no tunnel/EA/Fleet
network, and publishes only Hub/worker loopback ports (defaults 15098/15099).
Identity remains internal to that project. Both processes use Production policy,
non-root identities, read-only image filesystems, dropped capabilities and bounded
resources. Images are local-only (`pull_policy: never`); there are no build jobs.

Prepare these inputs in an explicitly selected **non-secret path/table env file**:

- `CHUMMER_HUB_PRIMARY_API_IMAGE` / `..._IDENTITY_IMAGE`: exact locally built image
  IDs containing the reviewed migration source, not the old incumbent images.
- `CHUMMER_HUB_PRIMARY_API_CONFIG_FILE` / `..._IDENTITY_CONFIG_FILE`: absolute
  private Production JSON files mounted read-only at `appsettings.Production.json`.
  Keep matching Identity admin credentials and the existing required account-erasure
  receipt key here, not in Compose arguments or the non-secret env file. The private
  chapter-worker credential belongs only in the Hub file. Do not copy a broad EA
  environment or unrelated provider credentials into either file.
- `CHUMMER_HUB_PRIMARY_API_TOKEN_FILE` / `..._IDENTITY_TOKEN_FILE`: absolute private
  restricted Teable tokens; never EA's broad credential. Only these two selected
  token files are mounted, not a credential directory.
- `CHUMMER_HUB_PRIMARY_API_TABLE_ID` / `..._IDENTITY_TABLE_ID`: distinct private
  tables with the revision schema and unique-key constraint described above. The
  Hub table hosts namespaced account/book/keyring streams; it is not an EA secret
  recovery table. Verify real credential/table scope before starting.
- `CHUMMER_HUB_PRIMARY_API_STATE_DIRECTORY` / `..._IDENTITY_STATE_DIRECTORY`:
  separate pre-provisioned private directories, never original recovery volumes.
  Ownership must match the explicit UID/GID (defaults 1000:1000). Use directory
  mode 0700 and private JSON/token file modes 0400 or 0600; reject symlinks.

The long bind syntax refuses automatic creation of missing host paths. Rendering
does not inspect secret contents or prove that permissions, image bytes or live
credential scopes are correct. Check the real inputs before any start:

```sh
docker compose --env-file /absolute/private-paths.env -f docker-compose.teable-primary-local.yml config --quiet
```

Do not run this from an ambient EA `.env` or use `down --volumes` against the old
project. No deployment command was executed as part of this change. Email starts
and auxiliary projection workers remain disabled for preparation; no FirstBook
worker/provider is launched. Starting this definition is not a public cutover,
email-login activation, publication or complete host-recovery claim. The real
authenticated account/book smoke and readiness readback still have to pass before
the existing Cloudflare tunnel can be deliberately switched.

Local state still includes install mirrors and auxiliary state outside the migrated
primary slices. Identity email-delivery history is now covered by the source slice
below, but it has not been deployed. Preserve local state until the
remaining custody/erasure work and complete cold-host recovery are proven; do not
assume every mounted state byte is a disposable cache.

13 focused tests render the actual Docker Compose model and check missing-input
rejection, primary wiring, isolated networking, loopback publication, selected
private mounts and absence of legacy PostgreSQL/certificate/broad-credential inputs.
They use synthetic paths/IDs and never build, create or start a container. This
does not replace the runtime checks or provision any production token.

## Identity mail history and dispatch admission — 2026-09-23

`IdentityEmailDeliveryService` now follows the explicit Identity storage selector.
In Teable mode it uses the same restricted Identity transport/table, with a separate
`identity-email-delivery` stream and `chummer.identity.email-delivery-primary/v1`
snapshot. Recipient/provider mappings, guardrail events, webhook history and dispatch
fences restore without local files. Every read/mutation refreshes primary authority;
unavailable, malformed or regressing state never falls back to cached/local history.
The existing local mode remains available. The Identity health route now checks
delivery history as well as session storage; dependency-injection registration is
covered by a focused primary-mode test.

Before the first configured provider is called, the primary service commits a
pending dispatch keyed by the hashed ticket and bound to the message fingerprint.
Competing writers cannot both obtain admission. A pending/unknown outcome is never
automatically resent, switched to another provider or exposed as an inline preview.
Acknowledged acceptance can be read back after reconstruction without another send.
An uncertain storage write invalidates that instance until cold reconciliation;
finalization reads fresh state so an intervening webhook is retained, including a
bounce that arrived before the provider's acceptance response. Provider response
bodies and raw transport exception messages are no longer stored/logged as errors.

This is **at most one automatic dispatch per admitted ticket**, not exactly-once
delivery or an inbox-delivery guarantee. A crash after admission but before sending
can leave a ticket unsent and pending; no automatic recovery sends it. A user can
request a new login ticket through the normal throttled Identity flow. The 100-event
recent-history window does not trim dispatch fences. Primary snapshots have a
16 MiB bound and fail closed at capacity; archival/retention and historical erasure
are not implemented by this slice. No existing local history is silently imported.
Ticket strings, callback URLs and message bodies are not included in the snapshot.

47 focused local tests pass with clean affected Identity/API/test compilation.
They include the existing Identity/mail/webhook/admin cases and 16 new primary
cases: cold history/session restoration, one-time login completion, restored
cooldown, duplicate/conflicting admissions, uncertain writes before/after provider
acceptance, post-provider read failure, malformed state, no local fallback,
disabled-provider preview rejection and webhook ordering. Transport is simulated
inside a network-disabled Docker container. No real email, Teable mutation,
credential provisioning, browser action, service deployment, signing or Play upload
occurred. Full Hub cold startup and actual FirstBook narration remain open.

## Local runnable image preparation — 2026-09-23

Source `224e0fd99bb326eb838194c0367bed1f427e8751` has now been published locally
for both API and Identity. Both affected publish commands completed successfully
using SDK 10.0.111, cached dependencies and network-disabled Docker. This is the
same diagnostic package graph used by the focused tests, including the explicit
Core contracts/GM version `0.0.0-packageplane.candidate.shd1c6e3d22360c`; it is
not a new canonical package-plane seal or a claim about hosted CI.

Two local preparation images contain only the selected publish outputs, excluding
appsettings, environment files, key files and state. They use the runtime base
already pinned by the API recipe, include curl for the existing Identity health
probe, run as UID/GID 1000:1000 and are not uploaded to a registry:

- Identity: `sha256:c3ba01082a18a487e1365c7fdd4bc6d8586e7580d43f2444291a35f440e37838`
- Hub API: `sha256:dfbcd45375d0b5a51871a596035d96f9bafca84a7fe9f4b0d9d81526c3216269`

Selected image inspections confirm exact source labels, published DLL/dependency
hashes, omitted config/state and .NET runtime 10.0.10. The private local build packet
retains the Docker recipe and input/output hashes. An initial Hub image attempt
failed because network-none changed the apt layer cache key; the subsequent build
reused the completed runtime layer with the original build network mode. No failed
attempt is described as successful or as runtime qualification.

Negative entrypoint checks used no network, no host port, read-only containers,
synthetic table IDs and an absent token path. Identity returned an unhealthy HTTP
500. Hub refused startup at primary credential-directory validation. These checks
do not establish successful configured startup, real account admission, remote
read/write scope or whole-host reconstruction. All temporary containers ended;
incumbent services, volumes, Cloudflare, mail and Play were untouched. Restricted
runtime tokens and private production configuration remain required before the
positive authenticated cold-start/book route can run.
