# Build Ghost Cloudflare Access ingress handoff

No live action was performed while preparing this edge. No Cloudflare Access
application, policy, DNS record, tunnel route, Docker network, running
container, provider gate, or provider resource was created or changed. This is
source plus offline proof for a later independently authorized operation.

## What this edge is

`build-ghost-cloudflare-access-edge` is an optional Compose-profile service.
The default private lane does not render, start, or attach it. Even with the
profile selected, the checked-in sentinel host/team values and empty audience
make the process exit before listening.

The edge has no host port. It may join only:

1. `build-ghost-private`, to reach the Presentation and AI services; and
2. one dedicated externally managed tunnel-ingress network, to receive traffic
   from a separately operated `cloudflared` container.

Do not attach Presentation, AI, the local Caddy edge, a database, or any other
container to the tunnel-ingress network. Do not attach `cloudflared` to
`build-ghost-private`. The Access edge is the sole bridge between those two
networks.

The edge admits only these exact route and method families:

* `POST /api/workspaces/import`
* `GET /api/workspaces/{workspace-id}`
* `DELETE /api/workspaces/{workspace-id}`
* `POST /api/workspaces/{workspace-id}/build-ghost/tool-access`
* `POST /api/v2/ai/build-ghost/tool`

The v2 path is not a direct proxy. It accepts only the existing
`chummer.build_ghost.private_tool_request.v2` body and exact tool-contract
header after an owner-bound grant has been observed at the issuance route in
this same edge process. It does not route v1, `/explain`, the internal packet
resolver, workspace mutation APIs, or neighboring Presentation/AI APIs.

## Security boundary

The edge requires exactly one canonical lowercase
`Cf-Access-Authenticated-User-Email` value and exactly one
`Cf-Access-Jwt-Assertion` value. It fetches public signing keys only from the
configured canonical `<team>.cloudflareaccess.com/cdn-cgi/access/certs`
endpoint with redirects, cookies, and proxy inheritance disabled. It verifies
RS256, issuer, exact configured audience membership, `iat`, `exp`, optional
`nbf`, signature, exact token type `app`, and exact equality between the JWT
email and authenticated email header. Cloudflare documents `app` as the
application-token type for both identity and service-token authentication;
this human ingress additionally requires the identity-only verified `email`
claim, so a service-token assertion cannot satisfy it. See Cloudflare's
[application-token contract](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/).

The edge applies a stricter local token policy than Cloudflare's full
configuration range: `exp - iat` may be at most exactly 86,400 seconds (24
hours). Cloudflare permits application or policy session durations up to one
month and defaults them to 24 hours; this edge deliberately accepts no token
longer than that default. Configure both the Access application and every
matching policy at 24 hours or less. See Cloudflare's
[session-duration contract](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/).

The upstream request is rebuilt from an allowlist. Client-supplied
`X-Chummer-Owner`, every `X-Chummer-Portal-*` owner/signature header,
`Authorization`, `Cookie`, `X-Forwarded-*`, and every `Cf-*` header are omitted.
Only the JWT-validated normalized email is injected as `X-Chummer-Owner` on
Presentation workspace/issuance requests. No owner header is sent to AI. The
v2 body is rebuilt with a fixed AI origin, fixed configured contract digest,
and no client owner, Access, authorization, cookie, forwarding, Cloudflare, or
trace headers. Request logs are disabled, the Access assertion is not
forwarded, and every response is `Cache-Control: no-store`.

The edge buffers only the 4 KiB grant request/16 KiB grant response and the
exact 16 KiB v2 request/64 KiB v2 response ceilings. After a successful grant
response, it retains only `SHA-256(packet_access_key)`, a domain-separated
SHA-256 reference for the validated owner, packet digest, and expiry in a
4,096-entry process-local registry. The raw key
exists only in the bounded request/response buffers, which are zeroed after
use. A matching owner/digest claim is removed before the one permitted AI
dispatch. Cross-owner attempts do not consume the binding. Restart, expiry,
replay, malformed/unknown keys, and absent bindings fail closed. A restart or
upstream failure after the Access claim can require issuing a fresh grant, an
intentional availability tradeoff that prevents Access-side key reuse.

The fixed local `410` is byte/content-type/cache equivalent to the current AI
terminal response. Presentation remains the final packet one-use, expiry,
workspace-revocation, revision, digest, locale, and request-kind authority.
Neither the edge registry nor the AI request receives an owner selected by the
client body.

Signing keys are cached for ten minutes. A missing `kid`, an expired cache, or
a failed refresh admits no key from the old generation. Concurrent callers
coalesce behind one generation refresh. Every refresh after a populated
generation, successful negative lookup, or failed attempt establishes one
global 30-second retry boundary. This is a constant-memory defense against
attackers rotating arbitrary unsigned `kid` values: at most one certificate
fetch is attempted in that interval, and no missing, failed, stale, or expired
key is ever returned. A failed unknown-key refresh may retain only previously
parsed keys whose original ten-minute lifetime is still current; a cold or
expired failure retains none. The bounded retry can temporarily reject a
just-rotated key after an earlier negative lookup; that is an intentional
availability tradeoff at this authentication boundary.

This grants an owner identity to the existing dev-header seam only for the
allowlisted Presentation routes. The exact v2 path consumes the existing
provider-neutral packet tool contract and returns the grounded deterministic
analysis/fallback packet; it never authorizes provider execution. The four
Tough Tongue gates remain literal `false`, and neither this edge nor its
configuration contains a provider account, key, token, or candidate resource.

## Later operator inputs

After independent security review, obtain these non-secret values from the
same Cloudflare Zero Trust organization and Access application:

```text
CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_HOST=<exact-lowercase-private-hostname>
CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_TEAM_DOMAIN=<team>.cloudflareaccess.com
CHUMMER_BUILD_GHOST_CLOUDFLARE_ACCESS_AUDIENCE=<exact-Access-application-audience-tag>
CHUMMER_BUILD_GHOST_CLOUDFLARE_INGRESS_NETWORK=<dedicated-existing-network-name>
```

The ingress-network variable uses Compose's strict `:?` interpolation. An
absent or explicitly blank value prevents even model rendering; there is no
implicit Docker network name and no chance of attaching to a similarly named
default network. Supply the exact already-created network name for every
Compose `config` or later profiled operation.

The application audience tag and team domain are identifiers, not bearer
credentials. Do not place the tunnel token, an Access service token, a user
JWT, a session cookie, or provider material in Compose environment or source.

Configure one Cloudflare Access self-hosted application for the exact private
hostname, with one explicitly intended human identity provider/policy. Do not
reuse a broader/root application, an `Everyone` bypass, or a service-token
policy for this human ingress. The tunnel ingress must target:

```yaml
service: http://build-ghost-cloudflare-access-edge:8080
originRequest:
  httpHostHeader: <exact-lowercase-private-hostname>
```

The final catch-all tunnel ingress rule must remain an explicit failure such as
`http_status:404`. Do not point the tunnel at Presentation, AI, the local Caddy
edge, a host port, or the internal resolver.

The separately managed tunnel Compose file should declare the same dedicated
external network and attach only its `cloudflared` service to that network.
Create or attach that network only in the later authorized operation; this
source change deliberately does neither.

## Pre-activation proof and stop boundary

From a clean reviewed Hub checkout, run:

```sh
./ops/build-ghost-private-nonprod/verify-cloudflare-access-edge.sh
```

The verifier runs static Compose/security tests, the dependency-free managed
JWT/proxy test harness, and `git diff --check`. It does not start Compose,
create or connect a network, contact Cloudflare, inspect credentials, or call a
provider. It fails closed unless the repository's `global.json` selects exact
.NET SDK `10.0.103` with roll-forward disabled. It never changes directory away
from that SDK authority before selecting or running the managed test project.
The narrowly path-scoped pull-request workflow installs that exact SDK and runs
the same canonical verifier. A local run with only another SDK is incomplete;
merge requires the exact-SDK pull-request job to be green.

Before any later activation, an operator must additionally prove all of the
following in one change-controlled window:

1. the Access application hostname and audience exactly equal the three public
   configuration values;
2. the tunnel sends the exact public Host header and its catch-all fails closed;
3. only `cloudflared` and this edge are attached to the dedicated ingress
   network;
4. the edge alone also joins `build-ghost-private`, with no host port;
5. missing, blank, duplicate, forged-signature, wrong-audience, wrong-email,
   wrong-host, wrong-method, v1, `/explain`, neighboring-path, internal-resolver,
   malformed-v2, header/body-ambiguity, oversized, replay, expired, restart,
   and cross-owner requests all fail before an unauthorized upstream dispatch;
6. a valid Access session can import, read, issue and consume one ephemeral v2
   packet grant, receive its deterministic fallback authority, and close only
   its own workspace;
7. upstream logs and request capture contain no Access JWT, Access email header,
client owner assertion, cookie, or authorization header; and
8. AI stays internal, deterministic fallback remains available, provider
   fields remain empty or their separately attested blocked values, and every
   provider/canary gate remains exactly `false`.

Stop before activation if any value is missing, any network member is
unexpected, any negative request reaches an upstream, JWT key retrieval is
redirected/unavailable, or any provider gate differs from `false`.

All three outbound HTTP transports explicitly set .NET's
`ActivityHeadersPropagator` to `null`. Ambient or inbound `traceparent`,
`tracestate`, `baggage`, `Request-Id`, and `Correlation-Context` values must be
absent at Presentation, AI, and the Cloudflare signing-key endpoint; the
offline loopback tests exercise the real `SocketsHttpHandler` instances for
all three boundaries.
