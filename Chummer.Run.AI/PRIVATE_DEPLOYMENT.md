# Private Build Ghost / Rook deployment

This service is an internal, read-only integration point. It is not a public
Tough Tongue endpoint and it is not a provider activation mechanism.

## Preconditions

Use an owner-only environment file outside the repository. It must contain the
private-tool endpoint, packet-authority endpoint, audience, service token, and
one internal API token. The container image must be addressed by a complete
`@sha256:<64 lowercase hex>` digest.

Run the preflight before starting anything:

```sh
python3 scripts/verify_rook_private_deployment.py \
  --image "$CHUMMER_RUN_AI_IMAGE" \
  --env-file "$CHUMMER_RUN_AI_ENV_FILE"
```

The preflight prints no credential values. A non-zero exit is a hard stop.

## Start and verify

The profile is intentionally separate from `docker-compose.public-edge.yml`:

```sh
docker compose -f docker-compose.rook-private.yml \
  --profile rook-private up -d
```

It publishes no host port and attaches only to the internal Fleet network. The
readiness route is authenticated and returns `503` until the packet-authority
endpoint and service credential are valid:

```text
GET /api/v1/ai/build-ghost/readiness
```

Use the internal bearer token for this probe. `/api/health` is liveness only;
it must not be used as deployment authority.

## Release boundary

The profile must remain stopped unless all of the following are separately
proven and recorded:

* immutable image and package-feed authority;
* packet-authority response and digest validation;
* private scenario/provider canary;
* durable audit and revocation path;
* explicit provider activation approval.

The checked-in profile forces Tough Tongue remote execution, canary access
grants, and every AI gateway provider to `false`. Do not override those values
from a mutable `.env` file without a new reviewed authority receipt.
