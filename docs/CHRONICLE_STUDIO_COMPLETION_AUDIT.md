# Chronicle Studio completion audit

Audited: 2026-08-12

This audit separates product behavior, provider declarations, live canary proof,
and release-toolchain proof. A narrow local check is never used as evidence for
an external action or platform build that did not occur.

## Requirement evidence

| Requirement | Authoritative evidence | Result |
|---|---|---|
| Authenticated AIWriteBook Tier 4 account | EA `config/provider_evidence/AIWRITEBOOK_ACCOUNT_REVIEW.source.json` | Verified read-only: AppSumo Tier 4, 5,100 displayed credits before canary, 5,000 monthly allowance, 2026-09-11 renewal |
| Sanitized capability, limits, privacy, and export declarations | Same tracked account-review source plus strict EA governance validation | Pass; no account address, credential, or secret value is stored |
| Live synthetic export canary | EA `config/provider_evidence/AIWRITEBOOK_EXPORT_ROUNDTRIP.source.json` | Pass: human-operated, 13 credits spent under an approved maximum of 18, private project, PDF/EPUB/DOCX verified, project deleted and inaccessible afterward |
| No unauthorized automation | Canary receipt, provider registry, and EA lane contract | Pass; unattended browser automation was not used and remains forbidden |
| GM-scoped Chronicle projects | `CommunityContracts.cs`, `CommunityStore.cs`, `GroupService.cs`, and authenticated controllers | Pass; creation, revision, packet access, and state transitions require a group manager role |
| Versioned source packets | `GroupService.ReviseChronicleProject` and Chronicle tests | Pass; every draft save increments the version, recomputes SHA-256, and appends digest/time history |
| Consent, spoiler, redaction, and source-rights gates | Separate persisted flags, source-approval validation, native/web controls, and packet text | Pass; every gate fails closed and runner handles require roster selection plus participant consent |
| Credit estimates | Captured provider price table and `EstimateChronicleCredits` | Pass as an estimate; the operator must still confirm the provider total before spending |
| Upload and generation approvals | `approve_upload` and `approve_generation` state transitions | Pass; packet download starts only after upload approval, generation separately requires an opaque provider-project reference, and neither action invokes the provider |
| Outline, publication, and external-send approvals | `approve_outline`, `approve_publication`, and `approve_external_send` transitions | Pass; each records a separate decision and performs no publication or send |
| Artifact provenance/import | HTTPS or traversal-safe `/artifacts/...` URL, SHA-256, PDF/EPUB/DOCX validation, provider reference, source digest, and import time | Pass; unrelated internal routes, dot segments, query-bearing relative paths, invalid URLs, digests, formats, and out-of-order imports fail closed |
| Player visibility | `IsPlayerVisibleChronicle`, `ToPlayerChronicleArtifact`, web rendering, linked Android controller, and Chronicle tests | Pass; a player-safe import remains hidden until the GM separately approves publication, player responses strip all source/provider/packet/credit/approval internals, and source-packet routes stay manager-only |
| Web surface | `Views/Groups/Detail.cshtml` and `GroupsController` | Pass; full draft, gates, approvals, packet, artifact, archive, roster, and invite workflow is server-rendered |
| Windows-compatible shared surface | `Chummer.Run.Contracts`, authenticated hosted routes, and 2,909-test runs on both `net10.0` and `net10.0-windows` | Pass at the shared-contract/hosted-surface boundary; no claim of a separate native Windows Chronicle editor |
| Native Android surface | Native five-destination Shell, Build list/detail flow, `CampaignPage`, linked-install client, `AndroidLinkedCampaignController`, Android arm64 build, compile gate, and Android contracts | Pass through an actual API 36 arm64 build; no Blazor/PWA or Play/Campaign `WebView` is used |
| EA governed lane | `verify_ltd_provider_lanes.py --lane aiwritebook_chronicle_studio --no-write` | Pass: `verified_draft_operator_lane`, no missing checks, runtime disabled |
| Durable receipts | Tracked account-review and round-trip sources plus strict validators | Pass on a fresh checkout; local downloads, source body, and operator-only artifacts remain private |

## Verification run

- Chummer Run API build: pass, zero warnings and zero errors.
- Chronicle Studio and linked-install tests: 21/21 within the full runs on both
  `net10.0` and `net10.0-windows`. These include the artifact-only player
  projection and linked Android packet-denial boundary.
- Full Chummer suite: 2,909/2,909 on `net10.0` and 2,909/2,909 on
  `net10.0-windows`.
- Native Android platform-neutral compile gate: pass, zero warnings and zero
  errors. Android contracts: 26/26. After the exact toolchain approval, the
  guarded bootstrap installed Android SDK/API and build-tools 36, platform-tools,
  accepted licenses, and a private Microsoft JDK outside the repository. The
  direct `net10.0-android36.0` arm64 Debug build passes with zero warnings and
  zero errors.
- The arm64 Release publish and pinned bundletool 1.18.3 validation pass. The
  current unsigned preview.3 AAB has SHA-256
  `ddb91078c07e342ff84d667897b2ca1f61e4bb1b2cee0305640c1e6c47370fce`;
  inspection confirms the expected package/version, API 24/36 bounds,
  permissions, privacy posture, app link, modern Back support, and arm64 payload.
- x64 Debug and linked x64 Release test packages also build with zero warnings
  and zero errors. Persistent host KVM access and emulator acceleration now pass.
  An accelerated API 36 AOSP device completed native Home, New runner, creation,
  metatype, Build, Play, Campaign, and More journeys; dice and condition-state
  persistence passed, Campaign stayed native, and repeated clean runs produced
  no crash-buffer errors. A non-reproducing ANR caused by rapid stale-coordinate
  test input is retained as harness diagnostic evidence.
- Play-managed installs use the native flexible Play Core update flow. Sideloaded
  builds stay in Chummer and explain that updates come through Google Play; the
  final device check emitted no browser, store, or external-activity launch.
- All nine Play listing screenshots were recaptured from the current native UI
  on accelerated API 36 x64 profiles and visually inspected. The five phone
  images are 1080×2400; the four tablet images are 1440×2560. They cover Home,
  Build, New runner, Play, Campaign, and More/native tools, and the asset
  dimension contract passes.
- A replacement upload key is provisioned outside the repository, and its
  owner-only recovery bundle passes EA table verification and a full restore
  drill (616 logical rows and 9 referenced files). The Play Console upload-key
  reset request was submitted with the replacement certificate and is pending
  Google's review.
- A fresh current-source arm64 preview.3 AAB is signed with that replacement key
  and passes all 26 Android contracts, bundletool validation, structural
  inspection, and signer verification. Its SHA-256 is
  `e36083b5c8861d66781585e98d97acd2379db6c53d9824a3cf8c5ffbce781e1a`.
  It cannot be uploaded until Play accepts the key reset, and its digest has not
  yet received exact-artifact upload approval.
- EA AIWriteBook governance, canary, provider-registry, and recovery tests:
  173/173. Account materialization and the offline PDF/EPUB/DOCX round-trip
  verifier pass. The lane verifier reports
  `verified_draft_operator_lane`, no missing checks, and runtime disabled.
- The full EA regression suite also passes: 6,060 passed and 27 skipped in
  44m24s, with no failures. Its two warnings are deprecations emitted by the
  installed WebSocket libraries during an existing real-browser E2E test.

## Explicitly unperformed actions

- Chummer and EA do not expose an unattended AIWriteBook execution route.
- No real campaign or runner data was uploaded during the canary.
- No canary publication or external send occurred.
- Chronicle approval actions record permission only; they never upload, generate,
  spend credits, publish, or send on their own.
- The upload-key reset request was submitted after explicit approval. No AAB was
  uploaded and no testing or production rollout was started. The current native
  screenshot set, signed preview.3 AAB, and accelerated device runs pass their
  local gates.

## Remaining proof boundary

The provider and Chronicle integration requirements are implemented and backed
by durable sanitized evidence. Provider-policy statements remain declarations;
the canary proves the observed private-project, export, credit, and deletion
journey but cannot prove undocumented backend behavior.

The native Android source now passes its platform-neutral gate, real SDK 36
builds, and an accelerated API 36 device journey. The structurally validated
unsigned AAB is retained only as superseded provenance because native source has
changed since it was built.

The registered preview.2 certificate and signed bundle still exist, but their
private upload key was not recoverable. A dedicated replacement key, verified EA
recovery bundle, and signed/inspected current-source AAB are ready; the Play
Console reset is submitted and still pending. Finishing publication therefore
requires Play acceptance and approval of the exact staged artifact before
upload. Every
pre-rewrite or pre-fix Android bundle remains superseded.
