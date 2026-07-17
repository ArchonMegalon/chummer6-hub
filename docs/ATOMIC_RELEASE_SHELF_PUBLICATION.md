# Atomic release shelf publication contract

Status: **P1 launch blocker**
Date: 2026-07-15

## Decision

Do not patch `ReleaseBundlePromotionService` with an app-only current-generation pointer.
That would make the HTTP upload lane atomic while silently orphaning the existing
filesystem, object-storage, nightly, workspace-mirror, and audit lanes that still
read or write the top-level downloads tree.

The release shelf needs one versioned, cross-repository publication contract. The
unit of publication is the complete shelf generation, and activation is one atomic
pointer change after all bytes and contracts have passed validation.

## Current deterministic gap

`Chummer.Run.Api/Services/ReleaseBundlePromotionService.cs` validates a complete
candidate under `.release-promotion-transaction-*`, then replaces these live entries
sequentially:

1. `files/`
2. `startup-smoke/`
3. `proof/`
4. `RELEASE_CHANNEL.generated.json`
5. `releases.json`

Rollback repairs the final filesystem state, but it cannot retract mixed bytes that
a concurrent reader already observed. The promotion lock serializes writers only.

The mounted downloads tree is not served by `UseStaticFiles`. Public reads go through
controllers and services, so generation-aware reads are feasible. They still require
version-bound URLs: a client can fetch an old manifest immediately before activation
and fetch a fixed `/downloads/files/<name>` URL immediately afterward. A per-request
pointer snapshot alone cannot keep those two HTTP requests coherent.

## Required generation layout

```text
<downloads-root>/
  .release-shelf-layout-v1
  generations/
    <generation-id>/
      activation-candidate.json
      RELEASE_CHANNEL.generated.json
      releases.json
      files/
      startup-smoke/
      proof/
      release-evidence/
      aur-packages.json            # when present
  current.json                     # the only mutable authority pointer
  RELEASE_CHANNEL.generated.json   # compatibility mirror only
  releases.json                    # compatibility mirror only
  files/                            # compatibility mirror only
  startup-smoke/                   # compatibility mirror only
  proof/                           # compatibility mirror only
```

`generation-id` must be an opaque, traversal-safe token and must never be reused.
`current.json` must contain at least:

- schema version;
- generation ID;
- release version, channel, and publication timestamp;
- SHA-256 of both manifests;
- artifact/proof inventory digest;
- activation timestamp and activation receipt ID.

Generation directories are immutable after activation. The pointer and its temporary
replacement must live on the same filesystem; activation uses an atomic rename, not
copy/delete. A malformed pointer or missing generation fails closed rather than
falling back to stale top-level bytes. Absence of both the layout marker and pointer
is the only allowed legacy fallback during the explicit filesystem migration. The S3
writer never performs a legacy copy; the same empty state is only first-generation
layout-v1 initialization.

### Canonical inventory digest

Layout-v1 inventory rows contain exactly `path` and lowercase `sha256`. Actual shelf
paths use portable ASCII segments matching `[A-Za-z0-9][A-Za-z0-9._+-]{0,254}`;
segments are separated by `/`, sorted ordinally, and must also be unique under ASCII
case folding. This makes Python collision handling identical to .NET
`OrdinalIgnoreCase`. Unicode values remain part of the serializer golden vectors but
are not accepted as physical inventory paths.

`inventoryDigest` is SHA-256 over compact UTF-8 JSON with object keys sorted
ordinally, array order preserved, and Unicode plus HTML-sensitive characters emitted
literally. Python uses `sort_keys=True`, separators `(',', ':')`, and
`ensure_ascii=False`; .NET uses `Utf8JsonWriter` with
`JavaScriptEncoder.UnsafeRelaxedJsonEscaping`. Both implementations must pass the
shared `atomic_release_shelf_inventory_digest_v1.json` golden vector before a pointer
can be committed.

## Version-bound public references

Authoritative manifests must reference immutable generation routes, for example:

```text
/downloads/g/<generation-id>/files/<file-name>
/downloads/g/<generation-id>/install/<artifact-id>
/downloads/g/<generation-id>/install/<artifact-id>/payload
/downloads/g/<generation-id>/install/<artifact-id>/metadata
/downloads/g/<generation-id>/proof/<path>
/downloads/g/<generation-id>/startup-smoke/<receipt>
/downloads/g/<generation-id>/release-evidence/<path>
```

Friendly routes such as `/downloads/install/<artifact-id>` and
`/downloads/files/<file-name>` may remain current-generation dispatch aliases, but
they are not valid authoritative manifest URLs. Install/claim tickets must bind the
generation ID as well as the artifact ID. This prevents a manifest from generation A
being paired with same-named bytes from generation B after an activation.

Every manifest and relevant HTTP response exposes the generation ID. Consumers that
read both canonical and compatibility projections must reject unequal generation IDs.

The Registry document is the release-truth authority. The writers do not copy its
uploaded bytes unchanged: both the C# server writer and the Python/S3 writer apply the
same narrow, golden-tested generation projection. That projection adds `generationId`,
maps each artifact route from its Registry access class, rewrites other release URLs to
the same immutable generation, sorts object keys, and emits compact UTF-8 JSON with one
trailing newline. It must not re-derive supportability, proof freshness, rollout reason,
or public-trust posture. Non-canonical source paths (absolute URLs, encoding, query,
fragment, backslash, traversal, or nested `releaseProof.proofRoutes` lookalikes) fail
before staging. Only the exact top-level Registry-owned
`releaseProof.proofRoutes` evidence array is retained without generation rewriting.

`open_public` primary artifacts use immutable `/files/<file-name>` routes.
`account_required` primary artifacts use `/install/<artifact-id>` and payload roles use
their `/install/.../payload|metadata` routes. Retained raw `/files` aliases never bypass
that policy: anonymous access is allowed only for `open_public`; an account-required
current alias requires the account flow, while an immutable generation raw alias
requires a claim or ticket bound to that exact generation and digest.

## Reader migration inventory

### Runtime public edge

- `Chummer.Run.Api/Services/PublicReleaseManifestService.cs`
  - captures `current.json` once per HTTP request/operation;
  - keys its 30-second manifest cache by generation ID;
  - resolves canonical, compatibility, artifact, evidence, and proof paths from the
    captured immutable generation;
  - must not combine the runtime Registry projection with local bytes unless their
    generation/release identity matches.
- `Chummer.Run.Api/Controllers/DownloadsCompatibilityController.cs`
  - `/downloads/releases.json`;
  - `/downloads/RELEASE_CHANNEL.generated.json`;
  - `/downloads/get/{artifactId}`;
  - `/downloads/file/{artifactId}`;
  - `/downloads/files/{**path}`;
  - `/downloads/install/{artifactId}` and proof/supplemental variants.
- `Chummer.Run.Api/Services/WindowsProofInstallerService.cs`
  - currently reads `proof/windows` and `files` directly and must resolve the captured
    generation or an explicitly separate, versioned supplemental-proof authority.
- `Chummer.Run.Api/Services/AurPackageCatalogService.cs`
  - currently reads `aur-packages.json` and AUR sidecars directly; it must either join
    the generation or be declared a separate atomic catalog with its own pointer.
- `Chummer.Run.Api/Program.cs`
  - `/downloads/release-evidence/{**path}` must be generation-bound.
- All services/controllers that consume the singleton `PublicReleaseManifestService`,
  including `PublicLandingController`, `AccountsController`, `AuthController`,
  `InstallLinkingController`, `HubPageChromeService`, readiness services, and support
  projections, inherit the same captured generation.
- `docker-compose.public-edge.yml`
  - the `/downloads-source` bind mount remains the storage root, but the deployed image
    and mounted layout version must be compatible.

### Filesystem and operational readers

The following currently treat top-level paths as authoritative and must use a shared
`resolve-current-release-shelf` helper or the live HTTP canonical endpoint:

- `scripts/verify-releases-manifest.sh`;
- `scripts/verify_release_shelf_replacement.py`;
- `scripts/verify_downloads_version_marker.py`;
- `scripts/public_download_shelf_truth_gate.py`;
- `scripts/verify_next90_m144_hub_release_truth_alignment.py`;
- `scripts/final_gold_janitor.py`;
- `scripts/materialize_release_ready_receipt.py`;
- `scripts/materialize_public_release_snapshot_readonly_audit.py`;
- `scripts/verify_public_edge_observability_release.py` and post-deploy checks;
- `tests/RunServicesSmoke/Program.cs` and release verification fixtures;
- operator instructions in `docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md`.

Checked-in `Chummer.Portal/downloads` copies in `chummer.run-services`, `chummer6-hub`,
`chummer6-ui`, and `chummer-presentation` become non-authoritative source/mirror trees.
Their manifests must say which generation they mirror.

## Writer migration inventory

### HTTP/server writer

- `Chummer.Run.Api/Services/ReleaseBundlePromotionService.cs`, reached through:
  - `POST /api/internal/releases/upload-sessions/{sessionId}/complete` in
    `Chummer.Run.Api/Controllers/InternalReleaseBundlesController.cs`.
- `Chummer.Run.Api/Services/ReleaseBundleUploadSessionService.cs` remains staging-only;
  session deletion happens only after a durable activation receipt exists.
- The legacy `POST /api/internal/releases/bundles` route is permanently rejected; it
  cannot bypass staged-session admission, reconciliation, or completion receipts.

The server writer must build and validate the entire immutable generation, fsync as
required by the storage contract, atomically activate `current.json`, and then return
success. Cancellation and test checkpoints are honored only before activation. Once
the pointer rename succeeds, the publication is committed; no fallible post-activation
verification may turn the HTTP result into a retryable failure.

### Filesystem, S3, and mirror writers

- `scripts/publish-download-bundle-http.sh` already uses the server lane; it must verify
  the activation receipt and generation ID, not merely compare a mutable manifest. Before
  the first file upload it persists an owner-only, non-secret session handoff bound to the
  canonical manifest and exact inventory. It fsyncs `request_started` before the one-shot
  completion request and `completed` only after the successful response is durable. Any
  ambiguous outcome is reconcile-only and blocks a replacement session.
- `scripts/publish-download-bundle.sh` currently mutates deploy and mirror roots in
  place. Its mirror helper copies manifests before smoke/proof/artifacts. It must call
  the shared stage/validate/activate primitive and must refuse a layout-v1 root when
  running in legacy copy mode.
- `scripts/publish-download-bundle-s3.sh` implements only layout-v1. It writes every
  immutable generation object with conditional `PutObject` (`If-None-Match: *`), verifies
  its digest metadata, and commits `current.json` with a captured ETag CAS (or a
  conditional create for the first generation). The incoming `publishedAt` must be
  strictly newer than the active pointer. A competing publisher therefore wins exactly
  one pointer commit; the loser fails closed without overwriting either generation or
  pointer. The post-commit downgrade marker is also immutable. There is no legacy-copy
  opt-in or ambiguous fallback.
- Primary S3 activation is the publication commit point. A subsequent latest-alias or
  HTTP verification failure reports the primary generation as already committed so an
  operator cannot mistake the status for a safe blind retry. CDN validation still must
  prove the pointer and generation objects agree.
- `scripts/generate-releases-manifest.sh` is a producer only; it writes into a candidate
  generation, never an active root.
- `scripts/materialize-public-downloads-bundle.sh` and
  `scripts/sync_workspace_portal_manifest_mirrors.py` may create source/mirror copies
  only after activation and must preserve generation metadata.
- `scripts/runbook.sh` must route release mode through one of the generation-aware
  publishers and reject legacy direct mutation.

Equivalent publisher copies in `chummer6-ui` and `chummer-presentation`, plus the
duplicated Hub upload service in `chummer6-hub`, must move in the same contract change.
`chummer-presentation/scripts/publish-latest-nightly-to-downloads.sh` is also a writer
and may not target the live top-level shelf directly after layout-v1 activation.

Registry producers in `chummer-hub-registry/scripts/release/` own the release-truth
document. The activating writer owns the deterministic generation projection described
above and applies it identically to canonical and compatibility documents; Registry
producers do not activate the Hub shelf directly.

## Activation sequence

1. Acquire the server promotion lock and validate/create the durable root writer-policy
   marker with mode `server-journal-v1`. Every non-server filesystem publisher refuses
   a root carrying this policy; production local publication uses the staged HTTP API.
2. Read one current generation (or the legacy shelf before first migration).
3. Materialize a complete candidate in a same-filesystem temporary directory.
4. Apply the narrow Registry-owned generation projection to both manifests and bind
   every artifact, proof, smoke receipt, and evidence URL to the new generation ID.
5. Run all contract, digest, provenance, freshness, tuple-retention, and privacy gates
   against the candidate root only.
6. Write and verify `activation-candidate.json`; flush candidate files/directories.
7. Materialize the target pointer bytes and persist the same exact old/target pointer
   bytes and digests, release identity, and inventory binding in the owning upload
   session. A restart with only this session intent proves the prior pointer exactly and
   resets safely; it never searches for or removes arbitrary generations.
8. Persist the owner-only active barrier and immutable per-receipt prepared intent,
   fsyncing the receipt-history parent. If only the active barrier survives, recovery
   republishes and re-fsyncs its byte-identical history before resolving it.
9. Rename the candidate to `generations/<generation-id>`, make it immutable, and fsync
   the generations parent. A pre-pointer abort removes only this intent-bound,
   never-activated generation and fsyncs the parent again.
10. Write, flush, and atomically rename the new `current.json` over the old pointer, then
   fsync its parent directory.
   This is the sole publication commit point.
11. Persist an immutable committed outcome. Keep the active-intent barrier until the
    owning upload session has durably stored its result and acknowledges completion.
12. On first migration, persist the layout marker as a best-effort post-commit
   downgrade sentinel. `current.json` is independently sufficient; marker failure is
   a non-retryable warning and marker-without-pointer fails closed.
13. Return the activation receipt. Post-rename durability ambiguity is outcome-unknown,
    never a retryable failed publication; retry reconciles the exact stored intent.
    If recovery proves that `current.json` already contains the committed target, it
    writes/loads the committed outcome and durably removes the active acknowledgement
    barrier before reporting ready, so the next promotion is not stranded.
14. Update top-level and cross-repository compatibility mirrors after commit. Mirror
    failure is an operational warning, never a rollback of the authoritative pointer.
15. Retain prior generations long enough for in-flight responses and rollback. Garbage
    collection is generation-aware, never deletes current, and is independently tested.

## Migration and rollback sequencing

1. Freeze live publication while the contract is deployed.
2. Ship pointer-aware readers first. With no layout marker/pointer, they read the legacy
   shelf exactly as today.
3. Ship the staged HTTP writer and the `server-journal-v1` policy guard first. Every
   legacy filesystem, nightly, Python, and mirror writer fails closed when either the
   writer-policy marker or `.release-shelf-layout-v1` exists. S3 remains a separate
   object-storage protocol and never writes the local production mount; its writer has
   no legacy mode and treats an empty target only as first-generation initialization.
4. Materialize an initial generation from the currently validated shelf and compare it
   byte-for-byte/semantically with live HTTP truth.
5. Atomically activate the initial pointer, then write the layout marker as the
   post-commit downgrade sentinel.
6. Re-run public canonical, compatibility, proof, smoke, and artifact digest checks.
7. Unfreeze only the generation-aware lane.

Rollback is another atomic pointer activation to a retained, already validated
generation. An older application binary that does not understand layout-v1 must not be
started against a pointer-enabled root. Emergency binary rollback therefore requires
either a forward-compatible reader or a separately verified compatibility-mirror sync;
it must never delete the pointer and expose a partially updated mirror.

## Required test matrix

### Storage and pointer unit tests

- reject pointer traversal, absolute paths, malformed JSON, missing generation, digest
  mismatch, and layout marker without a valid pointer;
- prove same-filesystem pointer replacement is atomic under concurrent read/activate
  stress (readers observe only complete generation A or B);
- prove a request/operation keeps one generation snapshot after activation;
- prove manifest caches are keyed by generation and cannot return A for files from B;
- prove immutable generation files cannot be overwritten through the service.

### Promotion failure tests

- inject failure/cancellation at every step before pointer rename: pointer and public
  bytes remain generation A;
- inject pointer-write/flush/rename failure: A remains active and B is unreferenced;
- activate B successfully: response is success and no later check can convert it into
  a retryable failure;
- retry the same completion idempotently: it returns B's existing activation receipt
  and does not create/publish C;
- rollback activates retained A atomically without mutating A or B.

### HTTP concurrency tests

- continuously fetch canonical and compatibility manifests during activation and assert
  every response is valid A or valid B with a generation ID;
- follow each manifest's version-bound artifact/proof/smoke/evidence URLs while repeated
  activations run; every digest and generation ID must match the originating manifest;
- start a ranged/slow artifact response from A, activate B, and prove the A response
  completes from immutable A bytes;
- verify friendly install/file aliases resolve a single current generation and issued
  tickets/claims remain bound to that generation;
- verify cache/no-store/CDN headers do not allow `current.json` to outlive its contract.

### Cross-writer contract tests

- HTTP, filesystem, S3, nightly, and mirror publishers emit the same candidate inventory
  and activation record for the same fixture;
- C# and Python emit byte-identical Registry generation projections for the same golden
  fixture and reject the same malformed or ambiguous source routes;
- concurrent S3 publishers produce exactly one successful `current.json` CAS, immutable
  generation keys reject reuse, and post-primary latest failures report committed truth;
- every legacy writer refuses a layout-v1 target;
- producer-to-consumer tests feed Registry output through Hub candidate validation;
- a repository-wide gate fails if any release-mode script writes a top-level active
  manifest/artifact/proof path directly;
- deployment tests prove a pointer-aware binary cannot be replaced by an unaware binary
  without the explicit rollback/mirror procedure.

## Launch gate

Do not claim atomic release publication, and do not unfreeze blind nightly retries,
until all authoritative writers use the generation contract, all public manifest URLs
are generation-bound, and the concurrency/failure matrix passes in the deployed storage
topology. Pre-publication validation and rollback alone are necessary but insufficient.
