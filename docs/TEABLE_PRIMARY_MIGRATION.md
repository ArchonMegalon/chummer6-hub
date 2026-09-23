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
  overflow. Usage consumption and request-receipt creation remain separate
  commits: a receipt failure after consumption still needs recovery before
  cutover. This is not an end-to-end atomic request/dispatch transaction.
- Community profiles, principal mappings and groups now have an isolated primary
  implementation using the existing typed snapshot. Explicit synchronous scopes
  refresh at outer entry; nested account/group/identity-link/ledger/experience
  operations retain that snapshot. Conflicting or uncertain writes disable the
  instance. Unconverted legacy `Gate` callers and local-file consumers reject
  primary mode rather than using stale authorization or creating a local shadow.
  This slice is **not registered for production**: remaining Community consumers,
  campaign artifact persistence and historical erasure still need conversion.

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

Runtime credential preparation: the existing EA API token returned HTTP 403 from
the read-only `/api/access-token` metadata endpoint. It has not been deployed to
Hub. No existing BrowserAct profile is scoped to Teable; approval for a separate
local Teable profile and a dedicated base-scoped credential has been requested.
Do not reuse a GitHub/Play/provider profile or put the broad EA token in Hub.

## Remaining before production cutover

1. Finish Community consumer/DI conversion and remaining document/artifact
   stores. Origin jobs, private first-party documents, linked runner snapshots,
   MyFirstBook usage, Origin credit reservations, billing membership, Horizon
   usage and request receipts have primary implementations. Close the separate
   quota-consumption/request-receipt recovery gap. Publication-index/provider-output artifacts and other
   auxiliary stores still need custody review. The isolated Community slice is
   not a complete activation.
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
