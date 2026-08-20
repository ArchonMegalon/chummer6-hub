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
export CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN="$(openssl rand -hex 32)"
export CHUMMER_AI_INTERNAL_API_TOKEN="$(openssl rand -hex 32)"
docker compose -f docker-compose.build-ghost-private-nonprod.yml config --quiet
docker compose -f docker-compose.build-ghost-private-nonprod.yml up --build -d
```

Health proof:

```sh
curl --fail http://127.0.0.1:8080/api/health # only from inside the AI container
docker compose -f docker-compose.build-ghost-private-nonprod.yml ps
```

The local TLS root is runtime state, not source. Copy it to a mode-0600 temporary operator path and use `--cacert` plus `--resolve canary.chummer.run:8443:127.0.0.1` for canaries. A structurally valid but unknown fabricated key must reach the private authority and return `410` without creating a packet-store file; a wrong bearer/header pairing must return `401`. Also verify that a POST to `/api/v1/ai/build-ghost/explain` with the fabricated bearer still returns `401`; only the exact private-tool POST delegates to endpoint-owned authentication.

A positive request requires an owner-scoped workspace, a freshly issued five-minute `packet_access_key`, its exact packet digest, and the exact contract digest `sha256:473a30bae8bfdff67ca6bd925e51a499c953b2def8000917f2f2b017ba01f14b`. `run-local-canary.sh` creates and closes only a synthetic workspace, keeps the key in mode-0600 temporary files, expects `200`, `Cache-Control: no-store`, the exact `X-Chummer-Build-Ghost-Packet-Digest`, and schema `chummer.build_ghost_analysis.v1`, then replays the same request and expects `410`. It also verifies cross-owner rejection, the 15,000-character cap, forbidden-field absence, empty one-use grant storage, no raw key in service logs, all provider gates false, and a `404` after synthetic workspace cleanup:

```sh
./ops/build-ghost-private-nonprod/run-local-canary.sh
```

Never print or persist the key in shell history or receipts. This script proves only the loopback Caddy route and local internal CA. External DNS, public certificate routing, provider scenario changes, and production deployment are outside this lane.
