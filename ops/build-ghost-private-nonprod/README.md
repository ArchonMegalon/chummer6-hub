# Build Ghost private non-production lane

This Compose lane builds the pinned Hub AI and Presentation sources without reading either canonical dirty worktree. It binds TLS only to `127.0.0.1`, keeps every provider/remote-execution switch false, and persists opaque one-use packet grants in the Presentation-owned absolute path `/app/state/build-ghost-packet-access` on a private named volume. A no-network one-shot container exports only Caddy's public local root certificate into a separate read-only AI trust volume; AI never mounts Caddy's CA keys.

Set these paths and a fresh operator-local token (never add it to a repository file):

```sh
export CHUMMER_RUN_SERVICES_SOURCE=/absolute/path/to/the/isolated/hub
export CHUMMER_PRESENTATION_SOURCE=/absolute/path/to/the/isolated/presentation
export CHUMMER_CORE_ENGINE_SOURCE=/absolute/path/to/chummer-core-engine
export CHUMMER_HUB_REGISTRY_SOURCE=/absolute/path/to/chummer-hub-registry
export CHUMMER_MEDIA_FACTORY_SOURCE=/absolute/path/to/chummer-media-factory
export CHUMMER_UI_KIT_SOURCE=/absolute/path/to/chummer-ui-kit
export CHUMMER_RUN_SERVICES_REVISION="$(git -C "$CHUMMER_RUN_SERVICES_SOURCE" rev-parse HEAD)"
export CHUMMER_CORE_ENGINE_REVISION="$(git -C "$CHUMMER_CORE_ENGINE_SOURCE" rev-parse HEAD)"
export CHUMMER_HUB_REGISTRY_REVISION="$(git -C "$CHUMMER_HUB_REGISTRY_SOURCE" rev-parse HEAD)"
export CHUMMER_MEDIA_FACTORY_REVISION="$(git -C "$CHUMMER_MEDIA_FACTORY_SOURCE" rev-parse HEAD)"
export CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN="$(openssl rand -hex 32)"
export CHUMMER_AI_INTERNAL_API_TOKEN="$(openssl rand -hex 32)"
docker compose -f docker-compose.build-ghost-private-nonprod.yml config --quiet
docker compose -f docker-compose.build-ghost-private-nonprod.yml up --build -d
```

The AI image records those four exact clean revisions as OCI labels. A running
container is source-identified only when its image labels equal the four
operator-resolved revisions; an image build or canary result without that
readback is not deployment proof.

Governed Tough Tongue credentials and opaque SHA-256 account references may be
injected only through the five `CHUMMER_BUILD_GHOST_TOUGH_TONGUE_*` runtime
variables declared by the Compose service. Never put their values in this file
or Compose source. Supplying credentials does not activate provider use: remote
execution and all three canary gates remain literal `false`, while agent and
voice identifiers remain empty until their separate read-verification gates pass.
The optional `CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF` is a
non-secret exact pin and accepts only lowercase `sha256:` plus 64 hexadecimal
characters. It must match exactly one aligned account reference. Invalid,
missing, duplicate, cooling-down, or quota-exhausted pins fail closed without
falling back to a different account.

The source contract pins the read-only Tough Tongue client evidence observed on
2026-08-22 at deployment `dpl_2hoTJxqMKHBPTX9eyHoXX7cZ1o9i`. Premium live
avatars remain private-candidate-only: Anam uses provider value `anam`, HeyGen
uses `liveavatar`, both declare a `2x` minute multiplier, and both require the
`Landmass` model provider. Scenario readback must preserve the exact
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

The local TLS root is runtime state, not source. Copy it to a mode-0600 temporary operator path and use `--cacert` plus `--resolve canary.chummer.run:8443:127.0.0.1` for canaries. A structurally valid but unknown fabricated key must reach the private authority and return `410` without creating a packet-store file; a wrong bearer/header pairing must return `401`. The edge forwards only the exact private-tool POST and the three method-bounded synthetic-workspace canary routes. Neighboring AI routes and every non-resolver route on `presentation.canary.chummer.run` return edge-owned `404` responses before either application receives the request.

A positive request requires an owner-scoped workspace, a freshly issued five-minute `packet_access_key`, its exact packet digest, and the exact contract digest `sha256:473a30bae8bfdff67ca6bd925e51a499c953b2def8000917f2f2b017ba01f14b`. `run-local-canary.sh` creates and closes only a synthetic workspace, keeps the key in mode-0600 temporary files, requires `Cache-Control: no-store` on both the key-bearing grant and tool response, expects `200`, the exact `X-Chummer-Build-Ghost-Packet-Digest`, and schema `chummer.build_ghost_analysis.v1`, then replays the same request and expects `410`. It also verifies exact cross-owner fail-closed status, the 15,000-character cap, forbidden-field absence, empty one-use grant storage, no raw key in service logs, all provider gates false, and a `404` after synthetic workspace cleanup:

```sh
./ops/build-ghost-private-nonprod/run-local-canary.sh
```

Never print or persist the key in shell history or receipts. This script proves only the loopback Caddy route and local internal CA. External DNS, public certificate routing, provider scenario changes, and production deployment are outside this lane.
