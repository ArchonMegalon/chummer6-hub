# Build Ghost private non-production lane

This Compose lane builds the pinned Hub AI and Presentation sources without reading either canonical dirty worktree. It binds TLS only to `127.0.0.1`, keeps every provider/remote-execution switch false, and persists opaque one-use packet grants in the Presentation-owned absolute path `/app/state/build-ghost-packet-access` on a private named volume. A no-network one-shot container exports only Caddy's public local root certificate into a separate read-only AI trust volume; AI never mounts Caddy's CA keys. The provider contract is explicitly `provider-body-key-v2`: its exact 43-character canonical base64url `packet_access_key` body value is the sole external credential, so it does not depend on unproven stored `Authorization` header interpolation.

Set these paths and a fresh operator-local token (never add it to a repository file):

```sh
export CHUMMER_RUN_SERVICES_SOURCE=/absolute/path/to/the/isolated/hub
export CHUMMER_PRESENTATION_SOURCE=/absolute/path/to/the/isolated/presentation
export CHUMMER_CORE_ENGINE_SOURCE=/absolute/path/to/chummer-core-engine
export CHUMMER_HUB_REGISTRY_SOURCE=/absolute/path/to/chummer-hub-registry
export CHUMMER_MEDIA_FACTORY_SOURCE=/absolute/path/to/chummer-media-factory
export CHUMMER_UI_KIT_SOURCE=/absolute/path/to/chummer-ui-kit
export CHUMMER_RUN_SERVICES_REVISION="$(git -C "$CHUMMER_RUN_SERVICES_SOURCE" rev-parse HEAD)"
export CHUMMER_PRESENTATION_REVISION="$(git -C "$CHUMMER_PRESENTATION_SOURCE" rev-parse HEAD)"
export CHUMMER_CORE_ENGINE_REVISION="$(git -C "$CHUMMER_CORE_ENGINE_SOURCE" rev-parse HEAD)"
export CHUMMER_HUB_REGISTRY_REVISION="$(git -C "$CHUMMER_HUB_REGISTRY_SOURCE" rev-parse HEAD)"
export CHUMMER_UI_KIT_REVISION="$(git -C "$CHUMMER_UI_KIT_SOURCE" rev-parse HEAD)"
export CHUMMER_MEDIA_FACTORY_REVISION="$(git -C "$CHUMMER_MEDIA_FACTORY_SOURCE" rev-parse HEAD)"
export CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN="$(openssl rand -hex 32)"
export CHUMMER_AI_INTERNAL_API_TOKEN="$(openssl rand -hex 32)"
docker compose -f docker-compose.build-ghost-private-nonprod.yml config --quiet
docker compose -f docker-compose.build-ghost-private-nonprod.yml up --build -d
```

### Operator-verified Tough Tongue read-only configuration

With no operator input, Compose mounts
`tough-tongue-read-only-binding-contract.unconfigured.json`. That regular,
non-secret sentinel lets the four services start, but its schema is
deliberately invalid for EA live ops, the contract digest and all candidate
inputs remain empty, and all four provider gates remain literal `false`.
The sentinel is blocked evidence, never a readback or provider-readiness claim.

An operator may instead prepare one caller-owned mode-0600 JSON file with
schema `chummer.build_ghost.tough_tongue.runtime_config.v1`. It must contain
exactly six distinct `{account_ref, api_key, organization_ref?}` slots, one preferred opaque
account ref present exactly once in those slots, either raw provider refs for
all of `agent`, `voice`, `function`, `scenario`, and `live_avatar` or empty
strings for all five, and the absolute
mode-0600 path plus canonical SHA-256 digest of an operator-verified
`chummer.build_ghost.tough_tongue.read_only_binding_contract.v2` contract. The materializer
accepts only the documented `balance`, `subscriptions`, `v2/organizations`,
and `scenarios/{resource_ref}` GET allowlist used by EA live ops,
allows the optional organization context only when it is present on all six
slots (so slot alignment cannot drift),
requires `authority.operator_verified=true`, rejects pre-shaped candidate
digests, duplicate JSON keys, links, weak file modes, and unsafe dotenv
characters, and never contacts a provider.

The all-empty candidate form is an account-audit-only deployment and also
requires `account_selection_policy` to name the absolute mode-0600 path and
canonical digest of an active
`ea.tough_tongue.operator_premium_grants.v1` receipt. That receipt is
user-authority policy, not a provider plan-label readback. The current policy
qualifies a stable opaque account-ref hash after a grounded balance strictly
above 1100 minutes, retains that qualification for exactly 11 calendar months,
and expires at the exact boundary. Slot reordering cannot change ownership;
identity drift, an account-ref replacement, an expired grant, a superseded
decision, partial resource candidates, or invalid calendar arithmetic all fail
closed. A later balance drop during the validity interval does not revoke the
policy grant. This posture may set `readyForAccountSelection=true`, but always
keeps `readyForResourceBinding=false`, provider plan-label readback unproven,
and every runtime/provider gate false.

Keep that file outside the repository in a caller-owned mode-0700 directory.
For a full-lane Compose operation, materialize into the same private run
directory and use only the resulting env file:

```sh
python3 scripts/materialize_build_ghost_tough_tongue_runtime_config.py \
  --config /absolute/private/operator-runtime-config.json \
  --output-contract /absolute/private/run/runtime-contract.json \
  --receipt /absolute/private/run/runtime-receipt.json \
  --output-env /absolute/private/run/runtime.env
docker compose --env-file /absolute/private/run/runtime.env \
  -f docker-compose.build-ghost-private-nonprod.yml config --quiet
```

The materializer stages each output in an unnamed inode and gives it one final
name with an atomic no-replace link:
the mode-0400 contract snapshot first, then a mode-0600 receipt binding the
exact contract-file, environment-file, and output-directory identities, and
the credential-bearing mode-0600 environment file last. All
three outputs must be new paths in the same private directory. A crash cannot
leave a usable single-link env file without its already-durable matching
receipt. Do not source the Docker dotenv file into an interactive shell, print
it, commit it, or reuse the run directory after any failed materialization.

Both bounded deploy helpers implement the same path while retaining only the
secret-free receipt and exact Compose contract. Create one caller-owned,
canonical, mode-0700 evidence root outside the repository, then set its path
and the operator config before running either helper:

```sh
install -d -m 0700 /absolute/private/build-ghost-runtime-evidence
export CHUMMER_BUILD_GHOST_TOUGH_TONGUE_OPERATOR_CONFIG_FILE=/absolute/private/operator-runtime-config.json
export CHUMMER_BUILD_GHOST_TOUGH_TONGUE_RUNTIME_EVIDENCE_ROOT=/absolute/private/build-ghost-runtime-evidence
./ops/build-ghost-private-nonprod/deploy-ai-with-rollback.sh
```

They verify owner, mode, single-link inode identity, receipt evidence digest,
environment digest, and contract snapshot digest immediately before adding
the private env file to Compose. Every input and output path component is
opened without following symbolic links, and all three outputs are published
through one held private-directory descriptor; an intermediate path retarget
therefore cannot split the contract, receipt, and environment commit. The
credential-bearing environment is securely removed on helper exit only through
the materializer-recorded directory identity and environment digest. If that
directory path is retargeted, cleanup fails closed without erasing the
replacement target or claiming credential removal. Its mode-0400 contract and
secret-free mode-0600 receipt remain together in the
unique evidence subdirectory printed after a successful deploy, so Docker can
recreate the secret mount and an operator can audit its exact digest later.
If an already running AI carries a nonempty contract digest, a deploy without
this complete operator config fails closed; the helpers never reconstruct a
partial contract from container environment. They still keep all provider
gates false and do not run the provider probe.
The materializer receipt status `ready-for-read-only-probe` means only that
local inputs are internally consistent. A fresh EA live-ops
v2 six-slot GET-only receipt is still required before the
attester can accept provider readback; missing identifiers or contract truth
must remain blocked with zero provider mutations.

The AI image records its four exact clean source revisions as OCI labels. The
Presentation image records all six sources in its compatibility-tree build:
Hub, Presentation, Core, Hub Registry, UI Kit, and Media Factory. A running
container is source-identified only when its labels equal every
operator-resolved revision; an image build or canary result without that
readback is not deployment proof. The private Presentation Dockerfile is owned
by this bounded ops lane instead of assuming a branch-only file inside the
Presentation checkout.

## Bounded AI-only deploy and rollback

After the full lane exists, use `deploy-ai-with-rollback.sh` for an AI-only
revision change. Run the helper from the exact clean Hub worktree named by
`CHUMMER_RUN_SERVICES_SOURCE`; provide the same six absolute source paths and
four exact 40-character revision variables shown above. The helper obtains the
two internal tokens from the single running AI container without printing
them. When no verified operator config is supplied it carries only the
existing blocked provider inputs; it refuses to reconstruct a configured
readback contract from partial container environment. It refuses a dirty or
revision-drifted source, a rendered provider gate other than literal `false`,
IO `full avg10` above 10, less than 20 GiB free under `/docker`, or a build poll
interval above 15 seconds.

Only one helper may run on the host at a time. It acquires the fixed
host-local lock
`/docker/chummercomplete/.state/locks/chummer-build-ghost-private-nonprod-ai-deploy.lock`
nonblockingly and fails before inspecting or changing runtime state when
another deploy owns that lock.

Before starting the build, the helper resolves the running AI's full image ID,
creates a collision-resistant `chummer-build-ghost-ai:rollback-*` reference,
and verifies that the new reference resolves to that exact ID. The unique
rollback reference is operationally immutable: the helper never retags or
deletes it. It builds and recreates only `chummer-build-ghost-ai`; Presentation
and edge container IDs must remain unchanged. Postchecks require exact source
labels, AI health, all four provider gates false, a revision/digest-bound
authenticated deterministic fallback with no remote attempt, missing-auth
`401`, and loopback Caddy `/api/v1/ai/build-ghost/explain` `404`.

Immediately before activation, the helper re-resolves the rollback reference,
running AI container and image, and the Presentation and edge container IDs.
Any drift from the pre-build snapshot fails before the AI activation boundary.

If activation or any postcheck fails, the helper retags the preserved image to
the mutable `private-nonprod` deployment tag and force-recreates only the AI
service. It verifies the restored image and health but retains the unique
rollback reference. Cleanup of old rollback references is always a separate,
explicit operator decision; this helper never invokes Docker image/container
removal or prune operations.

```sh
./ops/build-ghost-private-nonprod/deploy-ai-with-rollback.sh
```

## Bounded Presentation-only deploy and rollback

Use `deploy-presentation-with-rollback.sh` only after the six source paths and
six exact 40-character revision variables above identify clean isolated
checkouts. This release helper additionally requires Presentation revision
`8090e53f6dd64794145d81d7698394e4881d0c02`, the exact remote-main squash being
deployed, and revalidates all six clean source trees after the build immediately
before activation. The helper and the AI deployer deliberately acquire the same
nonblocking host-local lock, so their activations cannot overlap. It applies
the same hard host limits: IO `full avg10` may not exceed 10, `/docker` must
retain at least 20 GiB, and the interruptible build is polled at least once
every 15 seconds.

Before building, the helper resolves the exact running Presentation image and
classifies it by the exact OCI label
`run.chummer.build-ghost.packet-store-schema=v2`. A structurally keyed-v2
store may proceed only when the running image already carries that exact
label; a missing or different label is a pre-v2 image and fails before the
build. After that admission check, it creates, verifies, and retains a
collision-resistant `chummer-build-ghost-presentation:rollback-*` reference.
Every candidate image is built with and checked for the exact v2 label, then
preserved before activation under a second collision-resistant immutable
`chummer-build-ghost-presentation:v2-recovery-*` reference. The helper verifies
that reference still resolves to the exact captured candidate image, derives
the Compose activation tag from that immutable reference immediately before
activation, and binds runtime postchecks and the success receipt to the
captured image digest rather than the mutable tag. It retains the recovery
reference on success, rollback, containment, and pre-activation failure. The read-only
packet-store preflight runs before the build and again immediately before
activation. An empty store without an authority marker is admitted
because the v2 application can initialize it. A nonempty store
without `state-authority.v2.json`, a v1/unknown schema, a symlink, or ambiguous
filesystem state fails before activation. For keyed state, every authority and
lifecycle file must also parse as a JSON object with its exact v2 schema; files
are streamed to `jq` without emitting or persisting their values. The preflight
never deletes, moves, or quarantines state and never emits its values. The application remains the
keyed-MAC authority and fails health closed on a wrong token, contract, or MAC.

Immediately before activation, the helper revalidates the rollback image, the
running Presentation container and image, AI and edge IDs, all four
literal-false provider gates, and the packet store. It builds and recreates
only `chummer-build-ghost-presentation`. Postchecks require the six exact
source labels, Presentation health, missing and invalid private-route auth
`401`, loopback-only edge binding, public `/explain` `404`, unchanged AI/edge
IDs, and a v2 lifecycle receipt. The synthetic proof has bounded network calls
and an outer 15-minute deadline; its EXIT cleanup cannot short-circuit before
temporary packet-key material is shredded. It resolves one grant and
requires replay `410`, then issues another grant, closes the workspace, and
requires the revoked request to return the exact same no-store terminal `410`.

If activation or any postcheck fails, every rollback path first stops the
candidate Presentation, proves that no matching Presentation container remains
running, resolves the mounted packet volume without following a symlink, and
reruns the structural preflight. An exact v2-labeled rollback image is eligible
only when this quiesced result is exactly empty or keyed-v2. A pre-v2 rollback
image is eligible only when the result is exactly empty and
`state-authority.v2.json` is provably absent. Unknown, unreadable, mixed, or
ambiguous state never reaches a retag or recreate. This quiesced check closes
the request-versus-rollback race for later v2 releases. Immediately before a
first-cutover pre-v2 restore, the helper repeats the empty-store/absent-authority
classification and proves that Presentation is still contained and attached to
the same exact packet-store mount; any drift enters containment instead.

If v2 authority exists or its absence cannot be proved, the helper never
retags or recreates a pre-v2 image. It stops and contains only Presentation,
verifies no Presentation container remains running, re-verifies unchanged AI
and edge identities plus all provider gates false, preserves the packet
volume, candidate image through its exact immutable v2 recovery reference, and
the old immutable rollback reference, and emits that non-secret recovery ref
in a fixed `recovery-required` receipt. The verified receipt is emitted only
after two terminal containment, neighbor, provider-gate, and recovery-reference
passes. Any failed retag, recreate, image
readback, health check, neighbor check, provider-gate check, or preserved-image
check immediately enters the same containment path. A restored container is
re-resolved after its health wait and must still be the exact same container on
the exact preserved image; an unhealthy, replaced, or uncertain
Presentation is never left running. A later retry must begin with the same
structural preflight: keyed-v2 state requires an independently built and
tested exact v2-labeled recovery image, while ambiguous or mixed state remains
blocked. Containment deliberately leaves no Presentation process running; a
separately authorized recovery action may use the named immutable candidate
recovery ref, must prove its health, and only then may rerun this normal deploy
helper. A failure
after a successful build but before activation may still
restore the mutable deployment tag without recreating the unchanged old
container because no candidate has touched the volume. Rollback tags are never
removed or pruned implicitly, and packet state is never rolled back or
discarded.

```sh
./ops/build-ghost-private-nonprod/deploy-presentation-with-rollback.sh
```

This helper is deploy tooling, not deployment evidence. Static tests do not
prove an image build, container recreation, store initialization, or rollback;
those receipts require a separately authorized serialized run.

Governed Tough Tongue credentials, opaque account references, preferred
account pin, and all five raw candidate refs may be injected only as one
complete materialized config described above. Never put their values in this
file or Compose source, and do not bypass the materializer with individually
exported provider variables. Supplying a complete config does not activate
provider use: remote execution and all three canary gates remain literal
`false`. The preferred account pin accepts only lowercase `sha256:` plus 64
hexadecimal characters and must match exactly one supplied account reference.
Invalid, missing, duplicate, cooling-down, quota-exhausted, contract-drifted,
or ownership-drifted inputs fail closed without falling back to another
account.

A historical client-bundle or subscription review is not current provider
truth. Premium live avatars remain private-candidate-only: an operator-verified
contract may admit the provider values `anam` and `liveavatar`, but a fresh
GET-only readback must still prove the selected provider and entitlement.
Scenario readback must preserve the exact
`appearance.live_avatar_id` and `appearance.live_avatar_provider` values; the
session runtime must derive `avatar_config.enabled`, `avatar_config.avatar_id`,
and `avatar_config.provider` from them. Raw provider avatar identifiers are
excluded from binding receipts. This is provider-managed speech animation, not
local lip-sync proof: MuseTalk and the local lip-sync lane are explicitly
deferred.

Pinned client bundles and Premium account status do not authorize or perform a
provider mutation. A Build Ghost live-avatar candidate still requires an exact
Rook avatar binding, the digest-bound schema receipt, verified Cartesia voice
binding, verified private custom-function binding, scenario readback, and all
runtime canary gates. Missing or drifted evidence adds a blocker and leaves
remote execution disabled. The 2026-08-22 read-only account review created no
scenario, avatar, session, function, or access grant.

Health proof:

```sh
curl --fail http://127.0.0.1:8080/api/health # only from inside the AI container
docker compose -f docker-compose.build-ghost-private-nonprod.yml ps
```

The local TLS root is runtime state, not source. Copy it to a mode-0600 temporary operator path and use `--cacert` plus `--resolve canary.chummer.run:8443:127.0.0.1` for canaries. A structurally valid but unknown fabricated key must reach the private authority and return indistinguishable `410` for both unknown and replayed credentials without creating a packet-store file. Provider v2 rejects any `Authorization` header, cookies, query strings, noncanonical keys, schema drift, and contract drift before calling Presentation; it requires the static request header `Cache-Control: no-store`. The legacy `/api/v1/ai/build-ghost/tool` route remains an exact bearer/key compatibility boundary with its original contract digest, but v2 never falls back to it. The edge forwards only the exact v1 and v2 private-tool POSTs and the three method-bounded synthetic-workspace canary routes. Neighboring AI routes and every non-resolver route on `presentation.canary.chummer.run` return edge-owned `404` responses before either application receives the request.

A positive provider request requires an owner-scoped workspace, a freshly issued five-minute `packet_access_key`, its exact packet digest, request schema `chummer.build_ghost.private_tool_request.v2`, and provider tool contract digest `sha256:af7b643855bbc2220be40bfadc8cb1e89ecdc324a787c771a353d74e85f01104`. The retained v1 bearer compatibility contract remains `sha256:473a30bae8bfdff67ca6bd925e51a499c953b2def8000917f2f2b017ba01f14b`; the two digests and routes are never interchangeable. `run-local-canary.sh` creates and closes only a synthetic workspace, keeps both keys in mode-0600 temporary files, requires `Cache-Control: no-store` on key-bearing grants, v2 requests, and tool responses, expects `200`, the exact `X-Chummer-Build-Ghost-Packet-Digest`, and schema `chummer.build_ghost_analysis.v1`, then replays the same v2 body and expects `410`. It issues a second grant before workspace close and requires its revoked request to return the exact same no-store `410` body as replay. It also verifies v1 compatibility, v2 header/body ambiguity rejection, exact cross-owner fail-closed status, the 15,000-character cap, forbidden-field absence, empty pending and claim state, durable v2 audit and revocation state, no raw key in service logs, all provider gates false, and a `404` after synthetic workspace cleanup:

```sh
./ops/build-ghost-private-nonprod/run-local-canary.sh
```

## Generated private deployment attestation

Static tests and deploy-helper output are not a current deployment claim. Run
the dedicated attester from a clean Hub checkout and give it a new path inside
an existing caller-owned mode-0700 directory:

```sh
python3 scripts/attest_build_ghost_private_nonprod_deployment.py \
  --output /absolute/private/receipt-directory/build-ghost-private-nonprod.json
```

The output is a new mode-0600 JSON receipt. The command exits zero and emits
the literal status `deployed-private-nonprod` only when one stable observation
binds all of the following:

* the exact running Presentation, AI, and edge container IDs, image IDs, image
  layer digests, and source-revision labels;
* the current Compose and Caddy source digests, their runtime-mounted source
  digests, the internal application network, and the sole
  `127.0.0.1:PORT -> 443/tcp` host binding;
* all four Tough Tongue execution/canary gates as exactly one literal `false`
  value each, both before and after the canaries;
* keyed-v2 packet authority with zero pending grants and zero claims before and
  after the synthetic packet-access journey;
* the bounded local packet-access canary plus a direct authenticated AI canary
  whose exact fallback text is returned with `remoteExecutionEnabled=false`
  and `remoteAttempted=false`; and
* one of two non-interchangeable team-truth modes: an account-audit-only
  runtime must retain the materializer's digest-bound, unexpired
  `ea.tough_tongue.operator_premium_grants.v1` user-authority policy with six
  exact opaque account slots, the uniquely selected qualified account,
  `readyForAccountSelection=true`, `readyForResourceBinding=false`, no provider
  plan-label claim, and every provider gate false; a future resource-bound
  runtime still requires a fresh EA live-ops GET-only ownership receipt.

The account-audit-only mode does not call Tough Tongue during attestation and
does not claim live-avatar, function, voice, scenario, or remote-execution
readiness. It proves only the still-valid user-authority account-selection
policy and deterministic local fallback. Empty candidates are valid only as a
complete set; a partial candidate set remains a hard blocker.

The production CLI has no repository, Compose project, canary, or live-ops
path override. Those authorities are fixed to this reviewed checkout, the
literal `chummer-build-ghost-private-nonprod` project, its checked-in canary,
and `/docker/EA/scripts/ea_live_ops.py`. The AI container must carry the exact
opaque account-ref set and preferred account ref plus candidate agent, voice,
function, scenario, and live-avatar refs. It must also carry
`EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST`. The attester hashes the
candidate refs, binds the resulting expectation digest and account count/set to
the live receipt, verifies that receipt's canonical evidence and receipt
digests, and requires the read-only contract digest to equal the deployed
opaque value. Missing or mismatched inputs cannot mint a deployment claim.
Candidate resource inputs are raw provider IDs, not opaque account refs: each
exact raw value is always hashed, and a pre-shaped `sha256:` candidate value is
rejected instead of being accepted as the digest of a different raw resource.

Any missing, stale, ambiguous, drifting, non-redacted, or non-passing evidence
produces status `blocked`, a null claim, a nonzero exit, and explicit
machine-safe blocker codes. The attester never changes a Compose service,
provider gate, provider resource, external grant, route, or publication. Its
packet canary creates and closes only the documented local synthetic workspace;
the Tough Tongue probe is strictly read-only. A blocked receipt is evidence of
the current blocker, not permission to activate a provider or widen access.

Never print or persist the key in shell history, logs, or receipts. HTTP request serialization necessarily carries it only in the bounded v2 JSON body; controller errors and receipts contain fixed reason codes, never the submitted value. Presentation hashes it for filename lookup, atomically moves the pending grant before semantic packet validation, and deletes the consumed file. Possession therefore grants at most one resolution during the five-minute window, exactly as v1 did when it duplicated the same key in both body and bearer header. This script proves only the loopback Caddy route and local internal CA. External DNS, public certificate routing, provider scenario changes, and production deployment are outside this lane.
