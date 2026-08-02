# Self-Hosted Downloads Runbook

Purpose: publish desktop artifacts to a self-hosted downloads surface and verify that `/downloads/releases.json` serves non-empty artifacts.

For the full active-head artifact set, including the hosted API bundle, use `ACTIVE_HEAD_RELEASE_ARTIFACTS.md`.

Registry note:
`/downloads/releases.json` is now treated as a compatibility projection.
The canonical promoted release record is `RELEASE_CHANNEL.generated.json`, materialized by `chummer6-hub-registry`.
When available, Hub may consume the registry runtime endpoint directly via `CHUMMER_RELEASE_REGISTRY_CURRENT_URL`
or `CHUMMER_HUB_REGISTRY_BASE_URL`; the file-backed manifest remains the fallback.
The public-edge Compose contract exposes `CHUMMER_HUB_REGISTRY_BASE_URL` as an
explicit opt-in with an empty default. For the private loopback-bound Registry
runtime lane, set it to `http://host.docker.internal:18093` only after the
Registry `CURRENT` response passes the exact publish-response verifier. A
review-required snapshot is an immutable staging denominator, not publication
or promotion authority.

## Prerequisites

1. Desktop bundle exists (`desktop-download-bundle` layout):
registry-generated `RELEASE_CHANNEL.generated.json`, compatibility `releases.json`, and `files/chummer-*`.
2. Portal serves `/downloads/releases.json` as a compatibility view from your storage topology and should carry the registry-owned `RELEASE_CHANNEL.generated.json` alongside it.
3. Use preapproved runbook/script paths from repository root (`/docker/chummer5a`).
4. `RUNBOOK_LOG_DIR` is mandatory and must name a caller-owned mode-`0700`, symlink-free,
persistent child of `/docker/chummercomplete/.state/public-edge-deploy-receipts`. Never place
cutover evidence in `/tmp`. `RUNBOOK_STATE_DIR` may pin other writable tool state (for example
`DOTNET_CLI_HOME`) to a known writable directory.

## Public-edge mutable storage preflight

The portal process remains non-root and defaults to UID/GID `1654:1654`. Before Buildx can retag the canonical image, the governed deploy writes a durable journal containing the exact prior overlay, image tags, portal and tunnel identities and running states, the externally approved candidate runtime-proof SHA-256, and the prior running portal's two independently measured proof-mount digests. It also preserves owner-only snapshots of the candidate proof and, when the prior portal was running, both prior mounted proof files. The deploy starts a uniquely named blue/green candidate and does not destroy the exact prior portal until the candidate runtime authority is durably committed and the transaction journal is retired.

Recovery first removes only the journal-named candidate after verifying its Compose project, service, and one-off labels. It then restores the exact prior overlay and tags. A prior portal that was absent remains absent; one that was stopped remains stopped, and neither state is subjected to an impossible in-container proof check. To restart a previously running portal, recovery temporarily installs the separately journaled prior proof bytes at the canonical bind source, starts the exact old container so Docker captures that old inode, atomically restores the candidate proof source, and verifies both old in-container mount digests before restoring the tunnel. Missing old authority, identity drift, or either proof mismatch remains fail-closed and retains the journal. The Compose service dependency still requires successful initialization during normal startup. This one-shot service has no network, a read-only root filesystem, `no-new-privileges`, all capabilities dropped except `CHOWN`, `SETUID`, and `SETGID`, and no secret mounts. It migrates the four named mutable roots (`chummer-run-api-state`, `chummer-release-upload-sessions`, `chummer-windows-proof-store`, and `chummer-windows-proof-upload-sessions`) and then creates and removes an owner-only probe as the configured portal identity. Symlinks and special files in those roots fail the preflight.

`/downloads-source` is a host bind, not a named volume. The initializer only creates and removes a probe there; it never changes host ownership or modes. Before deployment, the operator must grant the configured portal identity create, write, and delete access. Choose one governed host-side policy and verify it locally, for example:

```bash
# Simple dedicated-owner policy.
sudo chown -R 1654:1654 /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads

# Or preserve the current owner and grant an access/default ACL.
sudo setfacl -Rm u:1654:rwX,d:u:1654:rwX /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads
```

Do not make the downloads tree world-writable. If `CHUMMER_PORTAL_UID` or `CHUMMER_PORTAL_GID` changes, rebuild the app image with the matching Docker build arguments and update the host ownership/ACL before recreating the portal.

The read-only data-protection certificate, certificate-password file, and InstallLinking PostgreSQL runtime connection file are also outside the initializer's authority. On the host, each must be explicitly readable by the configured UID/GID while remaining inaccessible to other users (normally portal-owned mode `0400`, or a narrowly scoped ACL on a root-owned mode `0600` file). Never mount these files into the initializer. The guarded deploy wrapper and image-restore tool abort before portal recreation if the volume preflight fails.

The guarded deploy wrapper runs the strict public-edge source preflight and closed Compose runtime attestation before `buildx` can retag the local image. The latter makes the required PKCS#12, password-file, PostgreSQL credential, runtime-role, and release-shelf posture inputs fail before any build or portal quiesce. The operation selects exactly one posture: ordinary deploy uses `true/false`, the explicit first-shelf cutover uses `false/true`, and recovery-only reconciliation uses `false/false`; every other pairing is rejected. After the one-shot initializer, the wrapper starts the blue/green candidate by exact name, waits for its `/api/ready` healthcheck, and then requires `/api/ready/publication`, which additionally proves layout-v1 activation and the configured release-storage free-space admission thresholds. The candidate stays transactional through the full browser-backed postdeploy gate. Any ordinary failure invokes the same idempotent recovery command used after a hard crash; an uncertain recovery exits with status `70` and preserves its journal.

The flagship deploy also uses a non-destructive Data Protection path rotation. Runtime attestation
pins the portal and InstallLinking import job to `/app/state/data-protection-keys-v2`; the
initializer creates or revalidates that private directory for the configured non-root identity,
and the certificate-configured candidate generates or validates its encrypted ring there. On the current flagship
host, explicitly render `CHUMMER_PORTAL_UID=1000` and `CHUMMER_PORTAL_GID=1000` to match the
owner-only certificate/password files, legacy state, and downloads bind; the closed runtime
attestation requires the build, portal, tools, and initializer to agree on that identity. The
incumbent's
`/app/state/data-protection-keys` bytes remain untouched for exact-container rollback. See
[`DATA_PROTECTION_KEY_RING_ROTATION.md`](DATA_PROTECTION_KEY_RING_ROTATION.md). Legacy ring archival
or deletion is post-stability maintenance, never part of this deploy transaction.

## Recommended Production Topology

1. The canonical local-production lane is Mode C: stage the complete bundle through the authenticated HTTP upload session, require the `server-journal-v1` writer policy, activate one immutable layout-v1 generation, and verify its committed `current.json` pointer and public truth.
2. `CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR` and `RUNBOOK_MODE=downloads-sync` are limited to legacy development or source-candidate trees. They must never target the live production shelf and fail closed when a server-journal or layout-v1 authority is present.
3. Mode B object storage is a separate production topology only when its layout-v1 conditional-write and pointer-CAS contract is enabled; it is not a fallback that mutates the local production mount.
4. Start from [`docs/examples/self-hosted-downloads.env.example`](examples/self-hosted-downloads.env.example) and adapt it to your portal base URL and governed storage target.

## Install-linking PostgreSQL authority cutover and recovery

The public-edge stack uses a managed/external PostgreSQL authority; this Compose file deliberately
does not deploy a database. Configure distinct owner-only runtime and migrator connection files with
`SSL Mode=VerifyFull` and
`Root Certificate=/run/chummer-secrets/install-linking-postgres-server-ca.pem`. Set
`CHUMMER_INSTALL_LINKING_POSTGRES_SERVER_CA_FILE` to the reviewed provider CA bundle, and set
`CHUMMER_INSTALL_LINKING_POSTGRES_DNS_NAME` (without a trailing dot) plus
`CHUMMER_INSTALL_LINKING_POSTGRES_IP` to one certificate-SAN identity and its reviewed address. The
`Host` in both connection files must equal that DNS name. Pre-create the LOGIN role named by
`CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE`. The `prepare` phase migrates the schema and
grants that existing role; it never creates a LOGIN.

### Required DBA boundary before deployment

The database-administration boundary is evidence, not application deployment orchestration:

1. Establish point-in-time recovery and keep data-protection key custody independent from the
   PostgreSQL backup. Record the approved recovery authority as
   `postgres_pitr_or_governed_recovery`.
2. Run the governed `prepare` phase and the read-only `prove-authority-ready` job. The readiness
   proof requires the exact schema, complete monotonic commit chain, current runtime identity, and
   least-privilege grants. It accepts either a genuinely empty generation-0 authority or an already
   seeded, internally consistent authority; it records the authority state digest, generation, and
   commit count without exposing the protected envelope. The separate `prove-empty-authority`
   command remains mandatory for `import-local --confirm-empty-authority` and is never weakened.
   Then run the non-mutating local-store presence probe. The flagship isolated-v2 Data Protection
   cutover requires that probe to prove no local store exists and the boundary to record the
   `import_skipped_no_local_store` phase. Its accepted receipt must contain
   `importSkippedNoLocalStore=true` and `localStorePresentAtCutover=false`. If a local store exists,
   stop: a legacy snapshot cannot be imported with the new v2 ring through the flagship lane.
3. Run `validate` after prepare/import and retain its bounded operator receipt. Preserve the
   append-only phase journal, exact portal/tool image identities, operator container identities, and
   source/release/runtime-proof authority bindings.
4. Materialize the boundary with
   `scripts/materialize_install_linking_cutover_boundary.py`. Public acceptance fails closed unless
   the explicit no-local-store checkpoint is present and records
   `dataProtectionKeyRingPosture=isolated_v2_requires_no_legacy_import`. The tool records the
   governed DBA result; it is not a shell cutover shortcut and does not authorize direct Compose
   mutation.
5. Do not begin the application deployment until the boundary receipt is complete and independently
   reviewed. A failed prepare, import, or validation is recovered through PostgreSQL PITR or the
   governed recovery authority, never by replaying an ambiguous application cutover.

### Sole production application cutover

Production operators use only the durable blue-green transaction in
`scripts/deploy_public_edge_portal.sh`, launched exactly as documented in Mode C. The clean launcher
binds these externally selected authorities:

- `CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1`;
- `CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD`;
- `CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF`;
- `CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256`;
- `CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT`;
- `CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256`;
- `CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256`;
- `CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL`;
- `CHUMMER_RUN_SERVICES_SOURCE`;
- `CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT`;
- `CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR`; and
- the caller-owned `RUNBOOK_LOG_DIR` plus governed Cloudflare Access credentials.

The wrapper owns staging, durable journaling, candidate creation, readiness and browser proof,
promotion, commit, prior-runtime retirement, and failure recovery. Operators do not stop the portal
or tunnel, activate overlays, retag images, or recreate Compose services by hand. If an interrupted
transaction journal exists, a normal deploy reconciles it and exits without starting another
transaction. After re-establishing the same source and runtime-proof authorities, request explicit
idempotent recovery only with `scripts/deploy_public_edge_portal.sh recover`.

### Committed public-download sidecar retirement

Topology-B recovery and retirement are deliberately different operations. Use
`initial-release-shelf-public-download-cutover-recover` only to reconcile an interrupted cutover:
an uncommitted journal may return to its prior configuration, while a terminal committed journal
remains committed and its sidecar stays authoritative. Use
`initial-release-shelf-public-download-cutover-retire` only when an already committed sidecar must
be decommissioned in favor of the exact incumbent captured before that cutover.

Retirement requires `CHUMMER_PUBLIC_DOWNLOAD_OPERATION_ID` to name the existing committed operation
(the suffix after `chummer-public-download-`), not a new retry identifier. The clean launcher must
also receive the current source authority pins, the exact Cloudflare account and tunnel identifiers,
and `CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_FILE` as an absolute canonical path to an
owner-owned, single-link, readable, owner-only credential file. The wrapper validates file metadata
and passes only its path to the environment-scrubbed controller; neither the wrapper nor the
retirement receipts print credential content. If that governed credential path is unavailable,
retirement is blocked until an operator restores or supplies it through the approved secret lane.
Do not search arbitrary secret roots or copy credentials into a release workspace.

The retirement clean launcher must additionally use
`CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF=refs/remotes/origin/main` and supply
`CHUMMER_PUBLIC_DOWNLOAD_CANONICAL_PUBLISHER_SHA256` as the independently
computed SHA-256 of the exact UI
`scripts/publish-download-bundle-http.sh` that the flagship transaction will
use. This digest is public binding data, not a credential. A branch commit,
missing digest, or malformed digest blocks before the controller starts.

The retirement controller first binds the active authority to terminal `cloudflare-committed.json`
evidence and re-reads the live tunnel configuration at the exact committed target version and hash.
It then durably authorizes retirement, re-reads immediately before the PUT, restores the captured
`priorConfig` object and hash, and polls bounded configuration convergence. Connector authority is
the current Cloudflare connector set at each retirement transaction, not the set captured during
the original cutover: the controller reads Cloudflare's documented `SinglePage` connection
inventory without invented pagination parameters, requires its count and total metadata to prove
one complete bounded result, re-lists it on every poll, accepts safe additions and removals, and
requires every connector to report the exact restored configuration version in two consecutive
observations. It repeats that connector-set gate on resume and immediately before moving the
authority marker. After the marker is durably moved, a separate two-observation gate is mandatory
before sidecar cleanup; a crash between those steps resumes from the retired marker and re-runs the
post-marker gate. The original committed restoration and marker evidence stay immutable; later
observations use separate boundary/resume receipts, and the terminal receipt binds the marker-time,
first post-marker, and latest connector-gate hashes. If the immutable terminal receipt becomes
durable before its operation-journal entry, a rerun validates and adopts that exact receipt before
any connector re-verification or cleanup, preserving its original bindings. It also
proves HTTP 200 plus the exact captured body hashes and sizes for both
`RELEASE_CHANNEL.generated.json` and `releases.json` on `chummer.run` and `www.chummer.run`. Only
after the pre-marker gates and a final Cloudflare re-read does it atomically move
`public-download-active-runtime-authority.json` into the operation-private retired authority
receipt. Only after the separate post-marker gate does it clean the exact sidecar Compose project,
volumes, and candidate image.
Cleanup reconstructs the original runtime inputs from the journal and verifies the historical
Compose sources from the operation's captured Git commit, so a deleted sealed build workspace or a
newer controller commit cannot silently redefine the cleanup boundary.

An exit status of `76` means the outcome is intentionally uncertain and the authenticated shared
mutation lock remains held. During retirement, `SIGINT`, `SIGTERM`, Python `BaseException`, and any
nonzero controller result are all lock-retaining outcomes. `SIGKILL` cannot run a handler, so the
wrapper relies on the durable authenticated lock directory, not an inherited process file
descriptor; killing the wrapper cannot release that directory while a destructive child may still
be running. Inspect the durable receipts and process inventory, recover that exact lock through the
authenticated stale-lock procedure below only after every child has stopped, and rerun the same
retirement operation ID. A resumed retirement accepts only the exact committed target or the exact
restored prior config and never silently reapplies the sidecar target. Never delete, rename, or edit
the active-authority marker by hand.

After terminal adoption, the same locked controller writes two immutable,
content-addressed receipt files and then atomically replaces
`/downloads/TOPOLOGY_B_RETIREMENT.generated.json` as the commit marker. The
fixed file is a refreshable public envelope: its `generatedAt` records the
current materialization, while its content bindings retain the exact immutable
terminal completion receipt, latest post-marker receipt, retired authority,
canonical publisher digest, and terminal controller source commit. The
terminal source must be an ancestor of the clean current Hub `main` checkout;
advancing protected `main` therefore cannot rewrite terminal evidence.
Validation is type-exact: source heads and digests must be lowercase fixed
width strings, versions must be JSON integers (never booleans), timestamps
must be whole-second canonical UTC, and terminal paths must be normalized
absolute paths under the operation root.
Both the original post-marker connector receipt and an optional resume
post-marker receipt are pre-terminal evidence: their `verifiedAtUtc` must be
no later than the immutable terminal `completedAtUtc`. Envelope refresh only
revalidates and republishes those exact bytes; it never performs or invents a
later Cloudflare gate.

Content files use the platform's atomic exclusive rename
(`renameat2(RENAME_NOREPLACE)` on Linux or
`renameatx_np(RENAME_EXCL)` on macOS) after an owner-only single-link staging
file is fully written, set to `0444`, and fsynced. The target never has the
two-link crash window of link-then-unlink publication. The fixed envelope uses
an atomic replacement only after both content entries are durable. A crash
before either rename can leave an inert randomized staging file, but it cannot
block a retry or become the authoritative target. Directory creation and
publication use no-follow directory descriptors rather than path-based chmod.
The controller performs redirect-free, identity-encoded public readback of all
three exact byte streams before recording success.

An interruption before the fixed proof write leaves the previous complete
proof authoritative. A retry adopts the terminal local receipt and emits a
fresh envelope without contacting or mutating Cloudflare again. The 24-hour
freshness gate applies to this renewable envelope, not to the immutable
terminal completion time. The first refresh safely migrates an existing
materialization receipt from v1 to v2 while preserving every immutable
terminal and content binding.

Once those bytes are live, dispatch
`.github/workflows/topology-b-committed-retirement-proof.yml` from protected
Hub `main`. Provision its
`topology-b-committed-retirement-proof` environment for independent human
review, prevent self-review and administrator bypass, and allow only `main`.
The workflow has no secret and read-only repository permission. Its full
checkout proves that the immutable terminal source commit is an ancestor of
the exact protected `main` commit executing the workflow; equality is not
required. Its first attempt snapshots exactly three read-only files into the artifact
`topology-b-committed-retirement-proof-<run-id>-1`; the later UI publication
transaction authenticates that workflow run, current Hub main, source
ancestry, artifact metadata, archive digest, fresh envelope time, and exact
bytes through a Hub-scoped read-only Actions token. Do not manually create,
edit, or re-upload this artifact.

### Owner-native v4 successor cutover

A candidate-import v4 authority is a native-finalization identity and custody
bridge only. Its publication, upload, deployment, route, and code-deployment
authority fields remain false. Never reinterpret that bridge as serving
authority and never downgrade it to v3 to bypass the native evidence or
retained-incumbent bindings.

When the v4 candidate must replace an already active topology-B sidecar, use
this exact sequence:

1. Retire the existing sidecar through
   `initial-release-shelf-public-download-cutover-retire` with its original
   operation ID. The controller first verifies the hidden canonical portal on
   local port `8091`, its exact read-write canonical shelf bind, and both flat
   aliases for both public Host headers against the original committed
   incumbent baseline. This preflight records
   `canonicalShelfMutated=false`; it does not seed, copy, or rewrite the
   canonical shelf. The ordinary retirement then restores the exact prior
   Cloudflare configuration and frees the fixed sidecar port.
2. Preserve the retired operation root and its operation journal,
   `sidecar-shelf-receipt.json`, immutable generation tree,
   `retired-active-runtime-authority.json`, and terminal
   `topology-b-retirement.json`. Do not clean or edit these files. The
   successor validates their exact digest closure and uses that immutable
   generation—not the restored canonical primary—as the v4 retained incumbent
   snapshot.
3. From protected Hub `main`, dispatch
   `.github/workflows/public-download-successor-decision.yml` exactly once.
   The workflow accepts only a first-attempt `workflow_dispatch` whose actor
   and triggering actor are the same. In a sole-operator installation this is
   the provider-authenticated operator decision; no second reviewer is
   implied. The inputs bind the strict-v4 candidate digest, a fresh successor
   operation root and project, release/generation identity, the terminal
   predecessor retirement, and every surviving retained-custody digest.
   Supply the predecessor closure as the single
   `predecessor_binding_json` input in compact canonical JSON with exactly
   these sorted keys and no trailing newline:

   ```json
   {"operationJournalSha256":"<sha256>","operationRoot":"<absolute-old-operation-root>","projectName":"<old-project-name>","retainedGenerationId":"<old-generation-id>","retainedShelfTreeSha256":"<sha256>","retiredAuthoritySha256":"<sha256>","retirementSha256":"<sha256>","shelfReceiptSha256":"<sha256>"}
   ```

   Download the resulting one-file artifact without editing or repacking it
   and pin the exact downloaded archive SHA-256 and positive GitHub artifact
   ID.
4. Capture the actual Cloudflare tunnel configuration response after
   retirement, then run
   `scripts/release/public_download_successor_authority.py materialize`.
   Supply the downloaded decision artifact and digest, strict-v4 candidate
   authority and digest, terminal retirement receipt and digest, exact
   post-retirement Cloudflare response and digest, fresh operation
   root/project, protected-main source commit, GitHub artifact ID, account ID,
   and tunnel ID. Both materialization and later controller validation require
   outbound TLS to `api.github.com`; they live-read the fixed workflow-run and
   artifact resources and require the provider's artifact digest and size to
   equal the downloaded ZIP. Caller-supplied API JSON is not authority. The
   materializer rejects an expired or inconsistent decision, a reused retired
   operation root, missing retained custody, or a post-retirement
   configuration/version that differs from the terminal retirement. Its
   output is a single-use successor serving authority with the exact prior
   configuration and the freshly planned target configuration.
5. Launch a fresh
   `initial-release-shelf-public-download-cutover` operation with all normal
   clean-launch pins plus the three exact successor input pairs:
   `CHUMMER_PUBLIC_DOWNLOAD_SUCCESSOR_CUTOVER_AUTHORITY` and its `_SHA256`,
   `CHUMMER_PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT` and its `_SHA256`, and
   `CHUMMER_PUBLIC_DOWNLOAD_PREDECESSOR_RETIREMENT_RECEIPT` and its `_SHA256`.
   Also supply the provider's positive integer artifact ID as
   `CHUMMER_PUBLIC_DOWNLOAD_OPERATOR_DECISION_ARTIFACT_ID`. Supplying none
   preserves the v3 path; supplying anything less than all seven values fails
   before the controller starts.

The successor controller revalidates native executable custody from the exact
payload, scans the predecessor's preserved immutable generation for retained
bytes, and probes the newly prepared generation locally before Cloudflare
capture. Immediately before any route mutation, the captured Cloudflare
prior/version and planned target must equal the single-use successor
authority. The final active-runtime marker records that authority and its
candidate, decision, predecessor, and transition digests. Any mismatch,
expiry, missing retained file, occupied sidecar port, or uncertain retirement
state is a hard stop; resume the governed operation from its receipts rather
than editing authority files or routing by hand.

### Authenticated manual stale-lock recovery

The shared mutation lock never expires automatically. A failed acquisition remains a hard stop.
Only after an operator has used the process supervisor and Docker inventory to prove that no deploy,
restore, overlay activation, PostgreSQL operator job, or cutover shell still runs may the operator
recover the exact inspected lock. Run the recovery from the same clean-shell launcher boundary.
Independently select and verify the recovery tool SHA-256 before executing it.

```bash
lock_dir=/docker/chummercomplete/.state/public-edge-mutation.lock
recovery_tool=/docker/chummercomplete/chummer.run-services/scripts/recover_public_edge_mutation_lock.py
recovery_receipt_root=/docker/chummercomplete/.state/public-edge-lock-recovery-receipts
# Select the matching durable authorization file left by the interrupted lease receipt. Its name is
# `<actor>-<sha256-of-token>.owner-token` under the canonical recovery receipt root. Never copy,
# rename, print, or reconstruct it from the fixed lock.
: "${PUBLIC_EDGE_STALE_LOCK_AUTHORIZATION_FILE:?Export the matching persistent owner-token file}"
authorization_file="$PUBLIC_EDGE_STALE_LOCK_AUTHORIZATION_FILE"
: "${CHUMMER_PUBLIC_EDGE_LOCK_RECOVERY_TOOL_SHA256:?Export the independently selected tool SHA-256}"
[[ "$CHUMMER_PUBLIC_EDGE_LOCK_RECOVERY_TOOL_SHA256" =~ ^[0-9a-f]{64}$ ]]
test "$(/usr/bin/sha256sum -- "$recovery_tool" | /usr/bin/awk '{print $1}')" \
  = "$CHUMMER_PUBLIC_EDGE_LOCK_RECOVERY_TOOL_SHA256"
/usr/bin/install -d -m 0700 -- "$recovery_receipt_root"
test ! -L "$recovery_receipt_root"
test "$(/usr/bin/stat -c %a -- "$recovery_receipt_root")" = 700
test ! -L "$authorization_file"
test "$(/usr/bin/stat -c %a -- "$authorization_file")" = 600

# The capability was fsynced outside the lock before any Compose render/build mutation. Never print
# or recreate it from the stale lock: the external copy is the recovery authorization.
recovery_suffix="$(/usr/bin/date -u +%Y%m%dT%H%M%SZ)"

read -r lock_device lock_inode lock_mtime_ns < <(
  /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
    /usr/bin/python3 -I -c \
    'import os,sys; s=os.lstat(sys.argv[1]); print(s.st_dev, s.st_ino, s.st_mtime_ns)' \
    "$lock_dir"
)
read -r authorization_device authorization_inode authorization_mtime_ns < <(
  /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
    /usr/bin/python3 -I -c \
    'import os,sys; s=os.lstat(sys.argv[1]); print(s.st_dev, s.st_ino, s.st_mtime_ns)' \
    "$authorization_file"
)
recovery_receipt="$recovery_receipt_root/recovery-$recovery_suffix.json"
test ! -e "$recovery_receipt"
/usr/bin/timeout --kill-after=5s 60s \
  /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C HOME=/nonexistent \
  /usr/bin/python3 -I "$recovery_tool" \
  --owner-token-file "$authorization_file" \
  --expected-lock-device "$lock_device" \
  --expected-lock-inode "$lock_inode" \
  --expected-lock-mtime-ns "$lock_mtime_ns" \
  --expected-authorization-device "$authorization_device" \
  --expected-authorization-inode "$authorization_inode" \
  --expected-authorization-mtime-ns "$authorization_mtime_ns" \
  --minimum-age-seconds 900 \
  --reason "Interrupted public-edge mutation was manually inspected and is no longer running" \
  --confirm REMOVE_STALE_PUBLIC_EDGE_MUTATION_LOCK \
  --operator-attestation I_VERIFIED_NO_PUBLIC_EDGE_MUTATION_IS_RUNNING \
  --output "$recovery_receipt"
```

The tool first fsyncs an `in_progress` mode-`0600` receipt, rechecks the inspected lock and token
identities, atomically retires only a lock containing that authenticated owner token, removes the
external authorization, and then atomically fsyncs the `pass` receipt. It records only the token
digest, never the capability. A mismatched
identity, young lock, extra entry, missing manual attestation, or receipt error leaves recovery
failed closed. Preserve incomplete receipts for incident review.

Crash artifacts that no longer occupy the fixed lock are nonblocking but must not be deleted by
hand. For a digest-bound `.public-edge-mutation.lock.staging.<digest>` or
`.public-edge-mutation.lock.retired.<digest>` directory, inspect and capture the exact directory and
authorization device/inode/mtime values, then run the same clean command with `--mode orphan`,
`--orphan-path`, all three `--expected-artifact-*` values, and
`--confirm REMOVE_ORPHANED_PUBLIC_EDGE_MUTATION_ARTIFACT`. Omit `--orphan-path` and all artifact
identity flags only for an authorization-only orphan. For a legacy empty fixed lock with no
`owner-token`, use `--mode incomplete-lock`, the fixed-lock and authorization identities, and
`--confirm REMOVE_INCOMPLETE_PUBLIC_EDGE_MUTATION_LOCK`. These modes accept only the exact closed
partial shapes, retain the same minimum-age and no-active-mutation attestation, fsync an
`in_progress` receipt before removal, and produce a separate `pass` receipt. Any unexpected entry,
digest mismatch, identity drift, or nonempty tokenless fixed lock remains a hard stop.

The import service defaults to an invalid, non-mutating command. Keep that default. The explicit
`import-local --confirm-empty-authority` command belongs only to the governed DBA boundary after
the local-store probe and remote-empty proof. `prepare` and import are durable database changes;
an application deployment failure does not roll them back.

If the DBA boundary fails after a durable database change, use the recorded
`postgres_pitr_or_governed_recovery` authority and preserve its receipts. Do not restore a local
mirror over PostgreSQL, weaken TLS or role separation, or blind-retry an ambiguous import. Back up
the PostgreSQL authority and data-protection key material separately; both are required to recover
linked-account records.

## Mode A: Legacy/dev filesystem source candidate (shared mount; never production)

This lane exists only for legacy development, isolated source candidates, and migration rehearsal.
Its target must not be the live production shelf. The publisher refuses any target carrying
`server-journal-v1`, `.release-shelf-layout-v1`, or `current.json` authority; production uses
Mode C staged HTTP publication.

Repository variables (legacy/dev only):
1. `CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR`
2. `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` (or `CHUMMER_PORTAL_DOWNLOADS_PUBLIC_BASE_URL`)
3. `CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS=true`

Legacy/dev candidate path:
1. Build a complete desktop release bundle with registry-generated canonical and compatibility manifests.
2. Run `RUNBOOK_MODE=downloads-sync` only against the isolated candidate directory.
3. The publisher verifies the candidate, removes stale files only inside that selected nonproduction target, and verifies the selected candidate URL when configured.
4. Promote to production only by submitting the complete validated bundle through Mode C.

Manual nonproduction candidate command:
1. `RUNBOOK_MODE=downloads-sync DOWNLOAD_BUNDLE_DIR=<bundleDir> DOWNLOAD_DEPLOY_DIR=<isolatedCandidateDir> DOWNLOADS_SYNC_DEPLOY_MODE=1 DOWNLOADS_SYNC_VERIFY_TARGET=<candidateBaseOrManifestUrl> bash scripts/runbook.sh`

## Mode B: Object Storage Deploy (S3/R2 compatible)

Repository variables:
1. `CHUMMER_PORTAL_DOWNLOADS_S3_URI`
2. `CHUMMER_PORTAL_DOWNLOADS_S3_LATEST_URI` (optional)
3. `CHUMMER_PORTAL_DOWNLOADS_S3_ENDPOINT_URL` (optional; required for many R2/S3-compatible endpoints)
4. `CHUMMER_PORTAL_DOWNLOADS_S3_REGION` (optional, defaults to `us-east-1`)
5. `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL`

Repository secrets:
1. `CHUMMER_PORTAL_DOWNLOADS_AWS_ACCESS_KEY_ID`
2. `CHUMMER_PORTAL_DOWNLOADS_AWS_SECRET_ACCESS_KEY`
3. `CHUMMER_PORTAL_DOWNLOADS_AWS_SESSION_TOKEN` (optional)

Local release path:
1. Build the release bundle on the controlled release host.
2. If `CHUMMER_PORTAL_DOWNLOADS_S3_URI` is configured, run `RUNBOOK_MODE=downloads-sync-s3` to deploy the bundle after generation.
3. The runbook publishes only through the immutable layout-v1 protocol in `scripts/publish-download-bundle-s3.sh`. Generation objects are conditional creates, and `current.json` is a conditional create or ETag CAS after every object has been verified. There is no flat-shelf/legacy fallback switch.
4. An existing pointer must validate completely and the incoming `publishedAt` must be strictly newer. A marker without a valid pointer, an unreadable object, an immutable-key collision, or a lost pointer CAS fails closed.
5. The runbook verifies the live pointer and generation projection. If the optional latest alias or this post-primary verification fails after primary `current.json` committed, the command explicitly reports `PRIMARY_RELEASE_COMMITTED generation=<id>`; do not treat that nonzero exit as authorization to publish another release.

Manual path:
1. `RUNBOOK_MODE=downloads-sync-s3 DOWNLOAD_BUNDLE_DIR=<bundleDir> CHUMMER_PORTAL_DOWNLOADS_S3_URI=<s3://bucket/path> CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL=<portalBaseOrManifestUrl> [CHUMMER_PORTAL_DOWNLOADS_S3_ENDPOINT_URL=<endpoint>] bash scripts/runbook.sh`
2. `RUNBOOK_MODE=downloads-verify DOWNLOADS_VERIFY_LINKS=1 DOWNLOADS_VERIFY_TARGET=<portalBaseOrManifestUrl> bash scripts/runbook.sh`

## Daily Rolling Shelf

Use this path for the normal Windows/Linux rolling shelf:

1. Build only the platform artifacts required for the current verification pass.
2. Stage the downloads bundle.
3. Follow the complete Mode C authority and verification sequence below. Its implemented
   publication command is the staged upload-session lane:
   `CHUMMER_RELEASE_UPLOAD_SESSIONS_URL=https://chummer.run/api/internal/releases/upload-sessions RUNBOOK_MODE=downloads-upload-http DOWNLOAD_BUNDLE_DIR=/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads bash scripts/runbook.sh`.
4. Preserve the upload-session handoff and committed activation receipt. An ambiguous completion
   is reconcile-only and is never authority to start another session.

This runbook does not create channel, cadence, or emergency-override authority. Those decisions
remain external release-authority inputs; do not substitute an undocumented publish mode.

## Mode C: Live `chummer.run` HTTP Publish

Use this mode when the public site must expose both the rebuilt downloads shelf and the new proof/deep-link controller routes.

Repository variables:
1. `CHUMMER_RELEASE_UPLOAD_TOKEN`
2. `CHUMMER_RELEASE_UPLOAD_SESSIONS_URL` (the only upload endpoint authority; defaults to `https://chummer.run/api/internal/releases/upload-sessions`)
3. `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` (optional; defaults to `https://chummer.run/downloads/RELEASE_CHANNEL.generated.json`)
4. `CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_COUNT` (optional; defaults to `3`)
5. `CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_DELAY_SECONDS` (optional; defaults to `2`)
6. `CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_MAX_SAMPLES` (optional; defaults to `6`)

Required live sequence:
1. Publish the bounded code-deploy snapshot and deploy the updated public edge app without granting
   release publication authority. Start by running
   `scripts/release/verify_public_projection.sh --code-deploy-stage` from the five immutable,
   owner-approved authority inputs. This atomically publishes an authenticated `CURRENT.json` with
   `status=review_required`, `projectionStage=code_deploy_review_required`, code-deployment
   authority enabled, and release-upload authority disabled. The seven-output snapshot includes
   exact copies of both the Registry release-channel receipt and Fleet flagship-readiness receipt
   authenticated by the Hub proof. It also records any failing M120, desktop-native, M144, and
   live-Windows release gates as review blockers instead of relabeling them as passing. The deploy
   resolves its inputs from that same `CURRENT` snapshot and must not read a mutable sibling
   checkout.

   The release authority must independently select the exact merged commit, verifier digest,
   release-receipt digest, and candidate runtime-proof digest. Do not derive any expected value from
   the checkout, receipt, or proof path being executed. In particular,
   `CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256` is a required
   external authority input, not a value the deploy may obtain by hashing the live bind source.
   Place its one-line lowercase digest in an operator-owned, symlink-free mode-`0400` file outside
   the checkout, verify that file's custody, and pass the value and exact snapshot root explicitly
   through the otherwise empty `env -i` environment:
```bash
runtime_proof_authority=/docker/chummercomplete/.state/public-edge-deploy-authority/runtime-proof-bind-source.sha256
test -f "$runtime_proof_authority" && test ! -L "$runtime_proof_authority"
test "$(/usr/bin/stat -c %a -- "$runtime_proof_authority")" = 400
test "$(/usr/bin/stat -c %u -- "$runtime_proof_authority")" = "$(/usr/bin/id -u)"
IFS= read -r approved_runtime_proof_sha256 < "$runtime_proof_authority"
[[ "$approved_runtime_proof_sha256" =~ ^[0-9a-f]{64}$ ]]

/usr/bin/env -i \
  PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
  CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1 \
  CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD='<externally-approved-40-hex-merged-commit>' \
  CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF='refs/remotes/origin/main' \
  CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256='<externally-approved-verifier-sha256>' \
  CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256='<externally-approved-lowercase-sha256>' \
  CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT=/docker/chummercomplete/chummer.run-services/.codex-studio/published \
  CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256="$approved_runtime_proof_sha256" \
  CHUMMER_RUN_SERVICES_SOURCE=/docker/chummercomplete/chummer.run-services \
  /usr/bin/bash --noprofile --norc \
  /docker/chummercomplete/chummer.run-services/scripts/deploy_public_edge_portal.sh

unset approved_runtime_proof_sha256
```
   The deploy's postdeploy gate explicitly expects the review-required stage. It still verifies the
   candidate image, health, public routes, downloads shelf, navigation/PWA behavior, and release
   banner, but its receipt records `releaseReady=false` and `releaseUploadAuthority=false`. A
   postdeploy receipt that claims release readiness, or whose snapshot posture differs, fails the
   deploy and preserves rollback behavior.

   A passing code deploy does not create publication authority. If the intended Windows candidate
   is not already on the public shelf, do not rerun the full projection as a workaround: its live
   verifier deliberately requires the exact public `.exe`, payload, and sidecar bytes, while this
   review snapshot deliberately cannot upload or activate them. Candidate import is a separate,
   exact candidate-bound authority transaction. Only after that transaction publishes the candidate
   and the live verifier passes may the full projection advance `CURRENT.json` to `status=pass`,
   `projectionStage=release_upload_ready`, and `releaseUploadAuthority=true`. Until then,
   `/downloads/release-upload` and its command endpoint remain unavailable.

   The candidate-import transaction is intentionally one shot:

   1. Materialize the upload summary and `CANDIDATE_UPLOAD_INVENTORY.generated.json` from the exact
      files that the HTTP client will stage. Do not add, remove, or rewrite a bundle byte afterward.
   2. Run `scripts/release/materialize_candidate_import_authority.py` with that bundle, its exact
      `RELEASE_CHANNEL.generated.json`, the summary and inventory, and the finalized native-Windows
      evidence root. The materializer derives the exact Windows proof scope from the canonical
      `desktopTupleCoverage.requiredDesktopHeads` and requires fresh capture and accountable
      finalization provenance plus exact EXE, payload, candidate-inventory, and visual-proof
      bindings for that set only. A fallback head is not added unless canonical release truth
      requires it. Wine, stale evidence, a changed reviewer boundary, or any byte mismatch fails
      closed.
      For an unsigned stage-only v3 authority, omit `--windows-finalized-root`. For the owner-native
      v4 bridge, place the complete finalized tree at the selected publication stage's exact
      `proof/windows-native` directory and pass that same absolute directory through
      `--windows-finalized-root`. The materializer rejects a different root, a partial tree, an
      unlisted or extra file, changed embedded bytes, source-revision drift, or candidate manifest,
      inventory, installer, payload, or sidecar mismatch. Supplying that exact root changes only the
      authority contract to v4, adds `ownerNativeFinalizationBridgeAuthority=true`, and embeds
      `custody.nativeWindowsFinalizedEvidence`; omission preserves the existing v3 output.
      The v4 custody set has exactly ten content rows: the unsigned composition, four native
      provenance documents, the source release-channel and registry manifests, and the three final
      Windows candidate files. The two source manifests are the exact pre-projection bytes recorded
      by the v3 publication evidence; the Windows installer, payload, and sidecar are the exact
      final candidate bytes. The composition is also retained as an exact v4 publication-evidence
      file so the Hub can rederive every native candidate-content row.
      The native inventory and export bind the producer revision from
      `unsignedPublicationEvidence.sourceSha`. The native capture and finalization revisions must
      equal each other, but may be a later revision than that producer. The payload must be a valid
      ZIP with exactly one unencrypted regular root entry named `Chummer.Avalonia.exe`; the
      materializer streams that entry and derives its executable SHA-256 and size instead of
      trusting the native receipt's installed-executable claim.
      The finalization receipt's `captureArtifact.id` and `captureArtifact.sha256` remain
      authenticated UI-finalization attestation metadata. The live operator receipt must back those
      values with the GitHub API response and the downloaded artifact ZIP hash. The Hub validates
      their exact schema and cross-evidence consistency, but does not independently derive those two
      values from its local custody tree; do not describe that attestation boundary as
      Hub-derived.
   3. Independently hand off the resulting authority file's lowercase SHA-256, then publish it with
      `scripts/release/verify_public_projection.py --candidate-import-authority <authority> --candidate-import-authority-sha256 <approved-sha256>`.
      This advances `CURRENT` only to `status=candidate_import_ready`, with
      `candidateImportAuthority=true`, `codeDeploymentAuthority=false`, and
      `releaseUploadAuthority=false`.
   4. Use the normal staged HTTP client against that exact bundle. It supplies the authority-bound
      manifest, inventory, and bundle-identity headers on create, file, chunk, and complete requests.
      A Fleet credential proves caller identity but does not bypass `CURRENT`; candidate sessions are
      single-use even for Fleet, cannot invoke reconciliation, and reject a second session after a
      durable completion. Only an exact retry of the same completed session may replay its durable
      completion result.
      Candidate-authority v2 and v3 remain stage-only and cannot advance or activate a staged
      generation. A v4 authority may bridge finalization only when its root has exact contract
      `chummer.release-upload.candidate-import-authority/v4`,
      `ownerNativeFinalizationBridgeAuthority=true`, and exact finalized native-Windows evidence
      bound to the same candidate. The caller must use the Fleet internal token directly, not an
      upload ticket, and must repeat all four exact bindings:
      `X-Chummer-Candidate-Manifest-Sha256`,
      `X-Chummer-Candidate-Inventory-Sha256`,
      `X-Chummer-Candidate-Bundle-Identity-Sha256`, and
      `X-Chummer-Release-Exact-Incoming-Scope: avalonia:windows:win-x64`.
      That narrow owner bridge authorizes only
      `POST /api/internal/releases/stages/{stageReceiptId}/authority-advances` and
      `POST /api/internal/releases/upload-sessions/{sessionId}/activate-staged`.
      It never authorizes ordinary generation authority advancement, completion, reconciliation,
      direct bundle promotion, or rollback. The candidate binding is persisted in both stage and
      session receipts and must compare exactly again at activation.
   5. Run live convergence against the promoted bytes and publish a new full-pass projection before
      treating upload authority as restored. Candidate import by itself is never release readiness,
      never advances a stable/current release pointer, and never authorizes another candidate.

   Emergency rollback to a retained generation is a separate owner-only operation. First capture
   the active generation id and the exact committed authority revision id and snapshot SHA-256 from
   the server-owned active shelf while holding the normal operator boundary. Do not infer those CAS
   values from a stale browser page, do not hand-edit `current.json`, and do not reuse an
   idempotency key for different inputs. Rehearse the exact request without reading the owner token:

```bash
python3 scripts/rollback_release_generation.py \
  --target-generation '<retained-generation-id>' \
  --expected-current-generation '<active-generation-id>' \
  --expected-current-snapshot-sha256 '<active-authority-snapshot-lowercase-sha256>' \
  --expected-current-revision-id 'auth-<active-authority-revision-lowercase-sha256>' \
  --idempotency-key 'rollback-<unique-portable-operation-id>' \
  --dry-run \
  --output '/absolute/new/operator-receipts/rollback-dry-run.json'
```

   For the live call, use the caller-owned, single-link regular Fleet token file with mode `0600`
   and a new absolute receipt path:

```bash
python3 scripts/rollback_release_generation.py \
  --target-generation '<retained-generation-id>' \
  --expected-current-generation '<active-generation-id>' \
  --expected-current-snapshot-sha256 '<active-authority-snapshot-lowercase-sha256>' \
  --expected-current-revision-id 'auth-<active-authority-revision-lowercase-sha256>' \
  --idempotency-key 'rollback-<unique-portable-operation-id>' \
  --token-file '/absolute/owner-only/fleet-token' \
  --output '/absolute/new/operator-receipts/rollback-receipt.json'
```

   The client accepts only canonical `https://chummer.run`, refuses redirects, never writes the
   shelf or `current.json`, and creates the receipt with mode `0600` and no overwrite. A timeout or
   transport failure has unknown outcome: retry only the identical request with the identical
   idempotency key. Any changed current generation, authority revision, or authority snapshot fails
   the server-side compare-and-swap.

   The isolated public-download sidecar seeds its projection volume from the authenticated authority
   root, not from a flattened snapshot directory. The initializer accepts only the exact
   `candidate_import_ready` `CURRENT.json` selected by the controller and that pointer's immutable
   `public-projection-<sha256>` directory. It rechecks the pointer digest, snapshot tree digest,
   fixed candidate-output inventory, single-link regular-file posture, and generated `0644`/`0555`
   modes; symbolic links, extra material, or drift fail before the portal can start. The snapshot
   directory is installed first and `CURRENT.json` is renamed into place last, then the complete
   two-entry authority root is mounted read-only at `/public-projection`. Historical sibling
   snapshots in the operator-owned publication root are deliberately not copied into the runtime
   volume.

   - Do not use raw `docker compose ... up -d --build chummer-portal` for release publication. The guarded wrapper source-gates the audited checkout, builds `chummer-run-api:local` from explicit contexts, runs the volume initializer, starts a uniquely named blue/green candidate with `--no-build`, and postdeploy-gates its exact image id before durably committing the candidate authority. The exact old portal is retained for rollback until that commit.
   - Before upgrading the guarded deploy source across this journal-schema change, verify that `/docker/chummercomplete/.state/public-edge-deploy-receipts/active-overlay-transaction.json` is absent. If a legacy journal exists, recover it with the exact audited source version that created it; do not delete, rewrite, or pass it to the new recovery path, which deliberately fails closed and retains incompatible journals.
   - If a durable transaction journal exists, the wrapper reconciles it and exits without starting a new deploy. Rerun the deploy only after that recovery succeeds. To request idempotent reconciliation explicitly, repeat the authority-file checks above and use the same clean launcher, source-authority inputs, and explicit proof authority (release-receipt inputs are not required for recovery):
```bash
runtime_proof_authority=/docker/chummercomplete/.state/public-edge-deploy-authority/runtime-proof-bind-source.sha256
test -f "$runtime_proof_authority" && test ! -L "$runtime_proof_authority"
test "$(/usr/bin/stat -c %a -- "$runtime_proof_authority")" = 400
test "$(/usr/bin/stat -c %u -- "$runtime_proof_authority")" = "$(/usr/bin/id -u)"
IFS= read -r approved_runtime_proof_sha256 < "$runtime_proof_authority"
[[ "$approved_runtime_proof_sha256" =~ ^[0-9a-f]{64}$ ]]

/usr/bin/env -i \
  PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
  CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1 \
  CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD='<externally-approved-40-hex-merged-commit>' \
  CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF='refs/remotes/origin/main' \
  CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256='<externally-approved-verifier-sha256>' \
  CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT=/docker/chummercomplete/chummer.run-services/.codex-studio/published \
  CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256="$approved_runtime_proof_sha256" \
  CHUMMER_RUN_SERVICES_SOURCE=/docker/chummercomplete/chummer.run-services \
  /usr/bin/bash --noprofile --norc \
  /docker/chummercomplete/chummer.run-services/scripts/deploy_public_edge_portal.sh recover

unset approved_runtime_proof_sha256
```
   An exact-identity or old-proof-mount failure returns `70` and keeps the journal for investigation.
2. Verify the live bootstrap matches the deployed source and the legacy path redirects cleanly:
`bash scripts/verify-live-mac-bootstrap.sh`
3. For a Mac release runner, open `https://chummer.run/downloads/release-upload` in a signed-in browser, confirm the displayed authenticated `CURRENT` snapshot id and SHA-256, copy the generated `Command` block, and paste that exact command into the Mac shell. The command contains no upload ticket; mint a fresh short-lived code on the page and enter it only at the hidden prompt (or through the documented mode-`0600` ticket file). Do not run the raw `bootstrap.sh` URL for promotion because it has neither the upload credential nor the authenticated authority handoff.
   - For non-interactive intake, set exactly one token/ticket inline or `*_FILE`/`*_PATH` source. File aliases do not have precedence: multiple sources are rejected. The file must be absolute, operator-owned, regular, non-symlink, single-link, exact mode `0600`, and contain one UTF-8 value of at most 8192 bytes with at most one final LF. Its macOS ACL probe permits either no ACL or a sequential deny-only ACL made only of recognized entries and rights; it accepts the `@` permission suffix used when xattrs are present, including when followed by those deny-only ACL entries, and rejects allow, mixed, malformed, or unknown entries. Before launch, write and close a new compliant file and atomically rename it to the configured path; do not mutate that path or inode while the bootstrap runs. The bootstrap compares identity plus two bounded explicit-offset snapshots and rejects a single mutation observed by those checks, but finite rereads do not synchronize against an arbitrary hostile same-UID writer. The captured value is streamed to curl without persisting it in argv, a child environment, logs, or a config file.
   - The generated command derives and supplies these 17 immutable Hub-proof settings from the displayed snapshot: `CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT`, `CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT`, and the `PATH`, `EXPECTED_SHA256`, and `AUTHORITY` triplets for `CHUMMER_HUB_RELEASE_CHANNEL`, `CHUMMER_FLAGSHIP_PRODUCT_READINESS`, `CHUMMER_FLEET_QUEUE_STAGING`, `CHUMMER_DESIGN_QUEUE_STAGING`, and `CHUMMER_DESIGN_SUCCESSOR_REGISTRY`.
   - Do not export or override those 17 values on the Mac. The command creates owner-only temporary authority files, the bootstrap verifies every digest before invoking the local Hub generator, and the exit trap removes the files. Refresh the signed-in page whenever `CURRENT` advances.
   - The seven source repository `EXPECTED_COMMIT` pins remain independent, reviewed build inputs and must be exported before running the command. If the authenticated snapshot is missing, invalid, or lacks its complete authority inventory, the page and `.command` endpoint return `503` instead of falling back to a static proof or ambient sibling checkout.
4. Rebuild the current unified shelf bundle:
`bash scripts/materialize-public-downloads-bundle.sh`
5. Upload the rebuilt bundle to the live shelf:
`CHUMMER_RELEASE_UPLOAD_SESSIONS_URL=https://chummer.run/api/internal/releases/upload-sessions RUNBOOK_MODE=downloads-upload-http DOWNLOAD_BUNDLE_DIR=/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads bash scripts/runbook.sh`
   - If `CHUMMER_RELEASE_UPLOAD_TOKEN` is unset, the upload step now prompts for it with hidden input instead of requiring an inline shell assignment.
   - Canonical post-publish success is gated on stable public truth, not one transient read. `scripts/public_download_shelf_truth_gate.py` now cache-busts the live shelf and requires repeated consecutive matches against the local `releases.json` and `RELEASE_CHANNEL.generated.json` before the publish lane can pass.
   - Keep the default `3` consecutive live matches unless you are intentionally relaxing the guard for a non-canonical environment. Set `CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION=1` only if you intentionally want `releases.json` compatibility drift to fail the run.

Public-edge source and browser proof gate:
1. Release-ready must prove the public-edge source before it can claim a deployable edge. `scripts/verify_chummer6_release_ready.sh` runs `scripts/verify_public_edge_deploy_source.py` before the Windows visual audit.
2. The source gate fails when the deploy tree is dirty, untracked, behind upstream, or when `docker-compose.public-edge.yml` builds `chummer-portal` from a different source path than the audited checkout.
3. For live portal publication, use the exact clean launcher in the required live sequence above.
   A plain shell invocation, a self-derived `HEAD`, or a caller-selected Docker/Compose route is not
   deployment authority and is intentionally rejected.
4. When compose defaults point at machine-local paths, pin the audited source explicitly:
`CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT=/docker/chummercomplete CHUMMER_RUN_SERVICES_CONTEXT_DIR=chummer.run-services CHUMMER_RUN_SERVICES_SOURCE=/docker/chummercomplete/chummer.run-services python3 scripts/verify_public_edge_deploy_source.py --repo-root /docker/chummercomplete/chummer.run-services --compose-file docker-compose.public-edge.yml --compose-service chummer-portal --require-upstream --json`
5. The public-edge postdeploy gate must include browser-backed evidence for release claims:
`python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --skip-preflight --require-downloads-status-playwright --require-mobile-pwa-viewport-playwright --require-frontdoor-navigation-playwright --output .codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
6. The browser receipts prove downloads/status, mobile viewport fit, and the Open Chummer Build/Play navigation; the same aggregate also verifies PWA static assets including manifest-declared icon/screenshot/shortcut paths and service-worker-declared cache/shell paths, the mobile ledger opt-in/no-store boundary for Black Ledger heat, followed-world updates, and session continuity, the service-worker non-interference boundary, ProductLift iframe shell, and ready-mobile handoff JSON plus its route-backed player/GM/organizer packet links.
7. If `/service-worker.js` is served from the play shell instead of the portal worker, treat the deploy as a failed public edge even when mobile routes load. The expected live boundary is `shared_portal_root_worker`.
8. On the release host, also pin the mutable local image tag to the approved portal image id:
`python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --skip-preflight --expected-portal-image-id sha256:<approved-portal-image-id> --portal-container chummer6-hub-chummer-portal-1 --portal-image-tag chummer-run-api:local --output .codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
This catches local `chummer-run-api:local` retags that can otherwise restore stale or dirty bytes while public routes still partially respond.
9. The same aggregate emits the `flagshipHorizons` child receipt documented in `docs/FLAGSHIP_HORIZONS_GATE.md`; release evidence should show `flagshipHorizonsStatus=pass` and `flagshipHorizonsBrowserProofCoverage=full`.
10. If the runtime image guard fails, restore the portal without rebuilding it, then rerun the same postdeploy gate:
```bash
/usr/bin/env -i \
  PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
  CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1 \
  /usr/bin/python3 -I \
  /docker/chummercomplete/chummer.run-services/scripts/restore_public_edge_portal_image.py \
  --expected-portal-image-id 'sha256:<approved-portal-image-id>' \
  --image-tag chummer-run-api:local \
  --include-image-tags-matching '^chummer-run-api:pwa-direct' \
  --include-image-tags-matching '^chummer-run-api:current-source' \
  --include-image-tags-matching '^chummer-run-api:fixed-alias' \
  --compose-file /docker/chummercomplete/chummer.run-services/docker-compose.public-edge.yml \
  --env-file /docker/chummercomplete/chummer.run-services/.env \
  --project-name chummer6-hub \
  --portal-container chummer6-hub-chummer-portal-1 \
  --base-url https://chummer.run \
  --expected-release-channel '<approved-channel>' \
  --stability-window-seconds 120 --stability-poll-seconds 10 \
  --require-all-browser-proofs \
  --playwright-artifact-dir /docker/chummercomplete/chummer.run-services/.codex-studio/published/public-edge-browser-proofs \
  --output /docker/chummercomplete/chummer.run-services/.codex-studio/published/PUBLIC_EDGE_PORTAL_IMAGE_RESTORE.generated.json
```
The governed restore tool validates the approved image id, records Docker created time, tags, digests, and labels for any drifted image it replaces, repoints the configured mutable tag plus explicitly matched local aliases, runs the protected volume initializer, and performs the controlled portal replacement internally. It repairs bounded image drift during the optional stability window and retries the runtime image guard plus the downloads/status, mobile viewport, and Open Chummer navigation browser proofs in its postdeploy receipt while the container warms up.

Mac release bootstrap note:
1. The hosted mac bootstrap now defaults temporary packaging work to the run workspace and exports:
`CHUMMER_MAC_RELEASE_TMPDIR="$work_root/tmp"`
`CHUMMER_DESKTOP_INSTALLER_TMPDIR="$TMPDIR/desktop-installer"`
2. Override `CHUMMER_MAC_RELEASE_TMPDIR` when the default workspace volume is not the right SSD for `hdiutil` temp work.
3. Override `CHUMMER_DESKTOP_INSTALLER_TMPDIR` separately only when installer-image temp files must live on a different volume.
4. If a release ticket still fails with `hdiutil: create failed - No space left on device`, point `CHUMMER_MAC_RELEASE_TMPDIR` at a workspace-backed path on the target SSD and clear unneeded old `run-*` directories under the same parent before rerunning.

Dry run:
1. `CHUMMER_RELEASE_UPLOAD_DRY_RUN=1 CHUMMER_RELEASE_UPLOAD_SESSIONS_URL=https://chummer.run/api/internal/releases/upload-sessions RUNBOOK_MODE=downloads-upload-http DOWNLOAD_BUNDLE_DIR=/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads bash scripts/runbook.sh`

Required post-publish checks:
1. `https://chummer.run/downloads/RELEASE_CHANNEL.generated.json`
2. `https://chummer.run/downloads/install/avalonia-osx-arm64-installer`
3. `https://chummer.run/downloads/install/avalonia-win-x64-installer`
4. `https://chummer.run/downloads/proof/windows/current/artifacts/avalonia-win-x64-installer/installer`
5. `https://chummer.run/downloads/proof/windows/chummer-avalonia-win-x64-installer.exe`
6. `python3 scripts/public_download_shelf_truth_gate.py --base-url https://chummer.run --local-manifest /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/releases.json --local-canonical-manifest /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json`
   - Treat a publish as incomplete if the gate cannot prove the same promoted version on repeated live samples. A one-off match is not enough evidence for public truth.

Windows installer gold proof:
1. This proof is a native Windows visual/startup gate only. It must not publish downloads or promote a release.
2. Preferred remote path: run the native Windows proof runner from a controlled Windows host.
3. The runner captures the promoted installer startup receipt plus installer progress/completion screenshots, then exports a `windows-installer-gold-proof` bundle.
   Every bundle must contain both the native-Windows startup receipt and the visual-audit source plus its referenced screenshot bytes for the same promoted digest.
   Delivery must be a bounded zip whose proof tree includes `WINDOWS_INSTALLER_VISUAL_AUDIT.source.json`; loose folders and extra archive members are rejected.
4. Auto-captured screenshots are intentionally marked `review_required`; a human must inspect clipping/readability before changing those rows to `pass`.
5. Drop the exported zip into the ignored intake folder `.state/incoming_windows_installer_gold_proof/`, preferably named `windows-installer-gold-proof-<promoted-digest-prefix>.zip`.
6. Import the exported proof bundle from this repository root:
`python3 scripts/import_windows_installer_gold_proof_artifact.py windows-installer-gold-proof.zip --verify`
7. Refresh the current operator ask and digest-specific import command:
`python3 scripts/materialize_windows_installer_visual_audit_intake_request.py`
   - The current ask is written to `_completion/windows_installer_visual_audit/CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt`.
8. Watch for the bundle automatically from this repository root:
`python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --wait-seconds 900 --poll-seconds 10 --refresh-intake-request`
9. Local native-Windows fallback:
`scripts/capture_windows_installer_gold_proof.ps1 -LaunchInstaller -CaptureVisualAudit -ScaledDpiScale 1.5`
10. Manual screenshot fallback:
`scripts/capture_windows_installer_visual_audit.ps1 -LaunchInstaller -CaptureRequiredSet -ScaledDpiScale 1.5 -ClippingStatus pass -ReadabilityStatus pass`
11. Gold remains blocked until `scripts/verify_windows_installer_visual_audit.py` passes against the promoted installer digest.

Private Windows proof upload lane:
1. The durable proof shelf is mounted separately at `/windows-proof-store`; upload sessions use `/windows-proof-upload-sessions`. Neither path may overlap `/downloads-source`, which remains the canonical release shelf.
2. Keep `CHUMMER_WINDOWS_PROOF_UPLOAD_ENABLED=false` and `CHUMMER_WINDOWS_PROOF_CF_ACCESS_GATED=false` by default.
3. Confirm the Cloudflare Access policy covers the complete `/downloads/proof/windows` route family before setting both flags to `true` and recreating `chummer-portal`. Setting only one flag leaves the upload middleware unavailable.
4. Never publish proof bytes through `/downloads/supplemental/windows`, `/downloads/install/{artifactId}/proof`, or other aliases outside the protected route family.

Manifest-driven public route proof:
1. `python3 scripts/verify_public_routes_from_manifest.py --base-url https://chummer.run --manifest .codex-design/product/PUBLIC_LANDING_MANIFEST.yaml --output .codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
2. Local reverse-proxy variant: `python3 scripts/verify_public_routes_from_manifest.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --manifest .codex-design/product/PUBLIC_LANDING_MANIFEST.yaml --output .codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
3. The verifier checks public routes directly, checks anonymous fallbacks for registered routes without following the redirect, and emits a machine-readable JSON proof packet for publish or audit closeout.

Canonical domain posture:
1. `https://chummer.run` is the only hostname this runbook treats as publicly canonical and release-claimable.

## Release shelf layout-v1 cutover

1. Treat `.release-shelf-layout-v1` as a production downgrade sentinel: after layout-v1 has been activated, legacy flat-shelf readers and writers must fail closed.
2. Keep the canonical environment file at `CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED=true` and `CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED=false`. Do not hand-edit it to perform the cutover.
3. Invoke the clean guarded wrapper with operation `initial-release-shelf-cutover`. The wrapper selects `false/true` only inside that bounded Compose invocation, proves the marker and current pointer are absent without case-colliding aliases, requires no generation footprint, unresolved intent, or committed history, and captures a descriptor-stable complete legacy inventory.
4. Immediately before the first Docker candidate-start instruction, the wrapper durably records `candidate_start_requested`. State and final-evidence receipts are published from unnamed `O_TMPFILE` descriptors with no-replace linking and parent-directory fsync; an exact empty owner-only state directory is the only recoverable creation residue. Any failure from the start boundary is outcome-unknown: do not rerun the cutover. Invoke `recover`, which uses `false/false` so the existing server-journal authority may reconcile an exact initial intent without starting generation two.
5. The wrapper is an observer, never a release-shelf writer. The hosted service and `ReleaseBundlePromotionService` under the persistent, owner-only mode-`0600` `.release-shelf-promotion.lock` remain the only migration authority; the lock file is not removed after promotion. The wrapper accepts initial success only after exact marker bytes, `current.json`, the immutable generation and inventory, both manifest identities, `server-journal-v1` policy, and the matching committed intent/outcome receipt all cross-bind and every legacy payload byte is preserved.
6. A cutover-enabled candidate is never promoted to steady state. After committed verification, the wrapper retires it, renders and attests canonical `true/false`, starts a fresh candidate, and reruns `/api/ready/publication` plus the existing browser-backed postdeploy gates. Final completion binds the exact owner-only compose, readiness, postdeploy, and active-runtime snapshots plus their directory object identity. Later deploy commits and later legitimate release generations retain `complete`; inspection replays the historical receipt/evidence chain and checks only the current generic layout controls, persistent lock, and absence of an active intent. If the ordinary transition fails, recovery restores the prior steady runtime and leaves a documented committed safe handoff for an ordinary governed `deploy`.
7. Aborted and committed receipts are mutually exclusive terminal phases. A second cutover against layout-v1, an unknown prior outcome, a missing or forged prestate, noncanonical marker/current casing, contradictory receipts, or any unresolved journal fails closed before migration can begin.
8. The migration flag applies to the filesystem/server lane only. The S3 writer has no legacy mode: an empty target may receive its first conditional pointer, while any partial or ambiguous target is rejected.
9. Registry manifests are projected, not copied byte-for-byte. The C# and Python writers retain Registry release truth, add the generation identity, apply access-class-aware immutable routes, and emit the same canonical JSON bytes. Absolute, encoded, query-bearing, fragmented, or nested proof-route lookalikes are invalid inputs.
10. `account_required` artifacts are never anonymously downloadable through retained raw `/files` paths. Current aliases enter the account flow; immutable generation raw aliases require a generation-and-digest-bound claim or install ticket. Only `open_public` artifacts may use anonymous raw routes.

## Strict Test Gate Commands (host-side)

Use these when you want hard failures instead of soft-skips.

Prerequisite probe:
1. `RUNBOOK_MODE=host-prereqs bash scripts/runbook.sh`

Single wrapper command:
1. `bash scripts/runbook-strict-host-gates.sh [optionalTestFilter] [optionalFramework]`
2. If no framework is provided, strict wrapper defaults to `net10.0` to keep host runs on the cross-platform test leg.
3. Local strict stage defaults to `FullyQualifiedName!~Chummer.Tests.ApiIntegrationTests&FullyQualifiedName!~Chummer.Tests.Presentation.DualHeadAcceptanceTests&FullyQualifiedName!~Chummer.Tests.ChummerTest`; override with `TEST_LOCAL_FILTER` when needed.
4. Wrapper fails when tracked `git` worktree state changes during the run; set `STRICT_ALLOW_WORKTREE_DRIFT=1` only when this is intentionally expected.

Local tests:
1. `RUNBOOK_MODE=local-tests TEST_NUGET_SOFT_FAIL=0 TEST_DISABLE_BUILD_SERVERS=1 TEST_MAX_CPU=1 bash scripts/runbook.sh`
2. Optional offline attempt after successful restore cache: `RUNBOOK_MODE=local-tests TEST_NO_RESTORE=1 TEST_DISABLE_BUILD_SERVERS=1 TEST_MAX_CPU=1 bash scripts/runbook.sh`

Docker tests:
1. `RUNBOOK_MODE=docker-tests DOCKER_TESTS_SOFT_FAIL=0 DOCKER_TESTS_BUILD=1 bash scripts/runbook.sh`

## Expected Verification Outcome

1. `/downloads/releases.json` has `downloads` with at least one artifact.
2. `version` is not `"unpublished"` in deployment mode.
3. When `CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS=true` (or `DOWNLOADS_VERIFY_LINKS=1`), each artifact URL/file in manifest verification is reachable.
4. Portal `/downloads/` renders artifact links that return HTTP 200.
5. When the bundle ships `proof/windows`, the deployed shelf exposes both the proof dispatch routes and the direct proof files exclusively below the Cloudflare Access-gated `/downloads/proof/windows` boundary. Public `/downloads/install/{artifactId}` routes may dispatch users to that boundary but must never serve proof-store bytes themselves.

## Portal Status Meanings

The portal manifest/page now distinguishes operator states explicitly:

1. `published`: real self-hosted artifacts are available.
2. `unpublished`: manifest is intentionally empty; no builds have been published yet.
3. `manifest-empty`: manifest exists but lists zero artifacts; treat this as a deployment/manifest generation problem.
4. `manifest-missing`: portal cannot find the self-hosted manifest or local artifacts.
5. `manifest-error`: portal found `releases.json` but could not parse it.
6. `fallback-source`: portal is using `CHUMMER_PORTAL_DOWNLOADS_FALLBACK_URL` instead of self-hosted artifacts.

Operational expectation:

1. Production/self-hosted deploys should end in `published`.
2. `unpublished` is acceptable only before the first release or in local-dev output that intentionally keeps the repo fallback snapshot.
3. `manifest-empty`, `manifest-missing`, and `manifest-error` should be treated as operator failures, not user-facing “normal empty state”.
4. Published portal builds do not ship the checked-in `Chummer.Portal/downloads/releases.json` snapshot, so a missing storage mount should surface as `manifest-missing`, not as a fake `unpublished` release feed.
