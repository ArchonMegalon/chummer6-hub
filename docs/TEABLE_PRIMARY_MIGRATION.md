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
- Install-linking snapshot and Data Protection key repository adapters exist.
  Their production activation is not yet wired.
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

Both primary modes remain deployment work in progress, not a switch to enable on
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

## Remaining before production cutover

1. Community account data and remaining document/artifact stores. Origin chapter
   jobs are integrated in source, but full-book export artifacts/other stores are
   not yet proven host-independent.
2. Explicit API primary activation and remote key custody.
3. Erasure of historical private snapshots and orphan chunks. Identity account
   erasure currently rejects Teable mode rather than claiming a false deletion.
4. Restricted production credentials and complete configuration/secret custody.
   The bootstrap credential needs independent recovery outside its own base.
5. A cold reconstruction of the complete fresh Hub and owner/auth/book checks,
   followed by controlled cutover. Do not deploy only the Identity half.

Append-only hashes are not protection from a privileged table administrator.
This store is not a distributed read-lock/lease provider and does not authorize
Rook or guarantee automatic failover or zero data loss.
