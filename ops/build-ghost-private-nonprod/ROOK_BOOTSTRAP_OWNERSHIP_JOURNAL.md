# Bootstrap ownership journal — no runtime executor

`rook_bootstrap_journal.py` is a standard-library, host-local bookkeeping
primitive for a future additive private Rook bootstrap. It has no CLI, Docker
adapter, provider call, operation endpoint, credential input or readiness gate.
It neither changes the existing preflight/historical-authority helpers nor
duplicates Core character state or the live-support MAC journal.

## Binding and custody

Creation requires a new absolute private directory, the public admission SHA256,
and a strictly shaped baseline: original Presentation container ID/name/image ID;
packet volume name/CreatedAt/mountpoint; private network ID/name; and any admitted
Caddy volume names/CreatedAt/mountpoints. These are identity pins, not independently
verified runtime observations. Keep every retained/admitted resource out of
transaction ownership. Network/image deletion is never a supported resource kind.

The immutable header also binds a fresh transaction UUID, canonical path digest,
and directory/lock device and inode identities. Copies, relocations, substituted
lock files, symlinks, hardlinks, non-private permissions, malformed JSON, duplicate
keys and invalid event histories fail closed. The lock file is never unlinked or
recreated by normal operations.

Every caller mutation and reopen requires an exact externally held checkpoint:
`transactionId`, integer `revision`, and public document `sha256`. Store that
checkpoint durably **outside this journal's rollback domain** before any runtime
operation. The helper does not implement external checkpoint custody. A hash
chain is not a signature, independent attestation or protection against a trusted
operator/root rewriting both the store and its external checkpoint.

## API

Import with a trusted isolated Python toolchain; there is no operator execution
command for this module. Use the returned journal as a context manager.

| API | Contract |
| --- | --- |
| `Journal.create(path, admission_sha256, baseline)` | Exclusively create a new private store; never adopt/overwrite an existing one. |
| `Journal.open(path, expected_checkpoint, admission_sha256, baseline)` | Lock and validate exact external bindings; quarantine interrupted unobserved intents. |
| `checkpoint` / `snapshot()` | Defensive copies of current public bookkeeping; `deploymentReady` always false. |
| `resource_name(kind, role)` | Fixed canonical names for admitted addition roles only. |
| `intent(expected, kind=..., role=..., absence=..., image_id=...)` | Persist successful caller-observed absence before creation; return unique transaction/intent/admission/role labels. |
| `observe_created(expected, intent_id, observation)` | Persist the exact newly created identity and ownership labels; never adopt a retained resource. |
| `begin_rollback(expected)` | Enter rollback only with known outcomes; otherwise persist quarantine. |
| `rollback_plan(expected, current_baseline, observations)` | Return nonexecuting candidates from complete caller-supplied current observations, or no-target quarantine. |
| `confirm_removed(expected, intent_id, observation)` | Record successful exact-identity absence after an external action; never execute that action. |
| `finish_rollback(expected)` | Terminal bookkeeping only after all owned resources have confirmed absence. |
| `seal(expected)` | Terminal ownership bookkeeping with all creations observed; not a deployment/readiness success claim. |

Only new AI, private Edge, signed-in ingress and bounded initializer containers,
plus previously absent Caddy/live-support volumes, can receive intents. Container
images must be immutable IDs. A create intent requires explicit matching
`kind`, `name`, `querySucceeded: true`, `present: false`; an error is not absence.

Observations contain exactly `querySucceeded`, `present`, `resource`, `consumers`.
Container resources bind immutable ID, name, image ID and the four projected
ownership labels; `consumers` is `null`. Volumes have no immutable Docker object
ID: bind canonical name, CreatedAt, local driver/scope, no driver options,
mountpoint and ownership labels. Their `consumers` must be an explicit complete
all-state container-ID list, never inferred from a failed/missing query.

## Persistence and recovery

Every mutation uses CAS against the externally supplied checkpoint and the
re-read journal. Events have strict contiguous revisions, previous-document
digests and replay-validated monotonic transitions. The bounded canonical JSON
snapshot is written to a newly created 0600 temporary, file-fsynced, atomically
replaced within the same directory, then directory-fsynced before returning.
Initial directory creation also fsyncs its parent. Cleanup targets only an exact
temporary inode created by that attempt; collisions and unrelated files survive.

The stable 0600 flock provides cross-process exclusion for **this store**. An
RLock serializes owner-process calls and descriptor close. Fork-inherited handles
cannot operate; fork-child close does not unlock the parent's flock. The final
directory must be operator-owned 0700 and the filesystem must honor local flock,
atomic rename and fsync. A network filesystem or arbitrary copied backup is not
implicitly supported.

Any uncertain write/fsync/replace or interrupted persistence poisons the handle.
Do not continue planning from its cached state. Close and reopen only with an
independently retained exact checkpoint; malformed, replayed, stale or mismatched
stores have no auto-repair/adoption path.

- Crash before atomic replace: the old committed snapshot remains authoritative
  relative to its external checkpoint. Leftover `.pending-*` files are neither
  promoted nor broadly deleted. Runtime creation must not have started before
  the intent and external checkpoint were durably acknowledged.
- Crash after durable journal change but before external checkpoint custody:
  reopening with the old checkpoint fails closed. The file's own latest hash is
  not a substitute. Operator reconciliation is required outside this primitive.
- Reopen with an acknowledged intent but no recorded create result: persist
  `quarantined`, even if creation might actually have succeeded or never started.
  There is no scan/adopt/delete guess and no partial destructive plan.
- A confirmed created resource can enter `rollback`, then `closed` after exact
  absence acknowledgments. `sealed`, `closed` and `quarantined` are terminal.

Rollback candidate plans preserve the original baseline and all admitted
resources. Any missing, failed, foreign or mismatching observation produces no
targets. Owned containers use exact immutable IDs. Volumes with observed owned
container consumers are deferred until a new observation proves zero consumers;
foreign consumers quarantine the entire plan. Absence is acknowledged separately.
There is no broad project-down, name-prefix prune or retained-volume deletion.

## Remaining integration boundaries

No runtime action has been implemented or authorized. The future coordinator
still needs one canonical active transaction or an outer **project-wide** mutex:
different newly created store directories are not mutually locked. It must own
external checkpoint custody, authentic preflight/build inputs, create-result and
all-state consumer observations, and the exact execution/rollback policy.

Plans say `executionAuthorized: false` and `requiresFreshRecheck: true`. They are
not an atomic deletion permit. Recheck the exact identity/labels and consumers
immediately before any future executor action; especially volume name/CreatedAt
and public labels cannot prevent hostile replacement between observation and
deletion. The module neither proves observation authenticity nor resolves that
runtime TOCTOU problem.

Private journal-key custody/initialization, token compatibility, provider-disabled
activation, post-start health/network/port/TLS proof, grounded local canary,
signed-in ingress and honest provider/team truth remain unimplemented here.

## Daemon-free validation receipt

Base: `e60335553a77cb442c583aa2d5a5ad206b0ff667`. Exact focused command:

```sh
python3 -m pytest -q tests/test_build_ghost_bootstrap_journal.py
```

The first RED was a new-feature missing-module error (`1 error in 0.08s`), not
an existing-lane regression. Executable additional REDs reproduced concurrent
close, copied-store/replaced-lock replay, interrupted persistence, and temporary
name collision before their fixes. Tests also use bounded child processes that
exit before/after atomic replace; this is process-crash testing, not a claim of
power-loss testing on every filesystem. All metadata and files are synthetic;
there are no Docker, provider, credential, build or service operations.

Final frozen-source result: `72 passed in 0.61s`. Independent static review found
no remaining blocking issues after the regression fixes. Source SHA256:
`42681f5567ef3f5a7357b94193ac2a0db8a7143504d7abc7c4d780c67db72f1c`;
test SHA256:
`fd1e6d072b03d2ac668cfb9608b8f86cf488ece1c220f1a1ccc3c598fb3aae49`.
