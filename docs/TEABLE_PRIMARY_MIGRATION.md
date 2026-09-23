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

Runtime credential preparation: the existing EA API token returned HTTP 403 from
the read-only `/api/access-token` metadata endpoint. It has not been deployed to
Hub. No existing BrowserAct profile is scoped to Teable; approval for a separate
local Teable profile and a dedicated base-scoped credential has been requested.
Do not reuse a GitHub/Play/provider profile or put the broad EA token in Hub.

## Remaining before production cutover

1. Finish Community consumer/DI conversion and remaining document/artifact
   stores. Origin jobs and the isolated Community account slice are implemented,
   but full-book export artifacts/other stores are not proven host-independent.
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
