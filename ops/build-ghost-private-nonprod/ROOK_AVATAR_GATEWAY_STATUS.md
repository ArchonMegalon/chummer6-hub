# Rook Avatar Gateway status

This file records source posture only. It is not a deployment receipt, a
provider readback, or live authority.

## Independent status axes

| Axis | Current source posture | What would change it |
| --- | --- | --- |
| Implemented | **Yes, candidate source.** The Hub source contains the bounded context store, private controllers, credential separation, authority client, response validator, deterministic fallback, and focused tests. This remains a local port until separately reviewed and merged. | Review and merge can make the implementation part of Hub `main`; they do not change any later axis. |
| Tested | **Focused local verification required for each exact commit.** Checked-in tests cover cryptographic context references, TTL/capacity, scenario/session/nonce/idempotency binding, revocation and in-flight fencing, private credentials, authority-request binding, response bounds, source anchors, actions, and fallback. A source test result is not hosted runtime proof. | A digest-bound test receipt for the exact commit may establish a test fact, without implying deployability. |
| Deployable | **No.** The source is compiled into the private AI service, but the process-local store requires an explicit one-replica topology, the Core-owned typed resolver and page-backed anchor authority are not implemented, resealed, deployed, or evidenced, no Avatar environment is present, and neither private edge admits its routes. | A reviewed deployment transaction must consume an exact resealed Core authority package and add the missing private runtime topology and authority configuration, while retaining rollback and provider-disabled gates. |
| Provider enabled | **No.** `CHUMMER_AVATAR_GATEWAY_PROVIDER_ENABLED` is absent from the checked-in runtime and defaults fail-closed. Both existing Build Ghost provider execution and canary gates remain literal `false`. No account, agent, voice, function, scenario, or live-avatar readback is inferred from source. | Separate operator authorization plus grounded team-account/resource receipts and an exact runtime configuration are required. Merely setting service tokens is insufficient. |
| Live authoritative | **No.** There is no exact image/source-label readback, runtime canary for this gateway, provider transaction, or live request/response receipt. | A later reviewed rollout needs digest-bound runtime and provider evidence. Until then deterministic Chummer-owned fallback is the only honest behavior. |

## Security and exposure boundary

The provider-facing controller exists only below
`/api/internal/avatar/provider`; there is no `/api/v1/avatar` controller. The
checked-in private Caddy allowlist does not route either the provider or context
administration endpoints, and the optional Cloudflare profile does not gain
them. A distinct provider service token, a distinct context-administration
token, exact `Cache-Control: no-store`, explicit provider enablement, and the
single-replica store contract are all required before model binding.

An issued `context_ref` is 256 random bits encoded as canonical base64url and
expires after at most one hour. Its stored authority binds the owner,
workspace/revision, character, campaign, ruleset/runtime/source/custom/GM
fingerprints, scenario, scopes, and locale. The first accepted provider session
is sticky. Nonces are one-use, idempotency keys are payload-bound, and a rule
authority answer is bound to the exact gateway operation and complete internal
authority request digests. Revocation cancels the upstream request, removes
cached results, and rejects a result even if the upstream ignores cancellation.

Only read/navigation output is admitted. The response validator permits exact
local source routes and the exact read-only workbench route; it rejects direct
apply actions, unknown action types, ungrounded calculation steps, duplicate
JSON properties, non-JSON responses, stale revision/runtime/source bindings,
and invalid answer digests. Failure produces a digest-bound deterministic
fallback without source anchors or actions.

The Hub contains no static rule lookup and does not synthesize a resolved
answer. Its `IAvatarRuleAuthorityClient` is only an adapter edge for a later
Core implementation. A resolved request is not dispatched unless all four
Core authority bindings are present and exact: the typed-authority contract,
package identity, package version, and canonical package SHA-256 digest. Those
values are included in the authority request digest which every answer must
echo. They are absent from checked-in runtime configuration. Consequently the
current source always returns the deterministic `unavailable` envelope for a
rule question, with no anchors or actions, even if an endpoint and service
token were supplied independently.

## Remaining blockers

- Implement and prove the Core-owned typed rule resolver and page-backed source
  anchor authority at the exact private endpoint, reseal its package, and bind
  the exact package identity, version, and digest at deployment review.
- Decide and implement a durable audited multi-replica context/revocation store,
  or retain and operationally enforce exactly one replica.
- Admit the gateway only through a reviewed private-only topology; do not add
  it to the checked-in public or optional Cloudflare allowlists.
- Bind the exact team-account and resource receipts without activating provider
  execution, then verify deterministic fallback first.
- Produce exact source, image, configuration, canary, and request/response
  receipts before changing either the deployable or live-authoritative axis.
