# Android linked-account v2 bearer and request-proof contract

Status: implemented, private API contract; release authority still depends on the
Android and Hub package/release gates.

The v2 contract removes the installation grant secret from ordinary JSON and
from the signed proof payload. The existing `api/v1/android/linked` contract is
retained only for deployed Preview 10 compatibility and returns `Deprecation:
true` plus a `successor-version` link. New Android clients must use v2 after
their initial install-link credential exchange.

## Protected routes

Every route below is `POST`, rejects query strings, and requires the same v2
bearer and device-proof headers:

```text
/api/v2/install-linking/grants/status
/api/v2/install-linking/grants/refresh
/api/v2/install-linking/grants/revoke
/api/v2/install-linking/continuation/workspaces/list
/api/v2/install-linking/continuation/workspaces/upsert
/api/v2/android/linked/account/erase
/api/v2/android/linked/groups
/api/v2/android/linked/groups/create
/api/v2/android/linked/groups/{groupId}/update
/api/v2/android/linked/groups/{groupId}/invites
/api/v2/android/linked/groups/{groupId}/chronicles
/api/v2/android/linked/groups/{groupId}/chronicles/create
/api/v2/android/linked/groups/{groupId}/chronicles/{chronicleProjectId}/draft
/api/v2/android/linked/groups/{groupId}/chronicles/{chronicleProjectId}/actions
/api/v2/android/linked/groups/{groupId}/chronicles/{chronicleProjectId}/packet
/api/v2/android/linked/groups/{groupId}/chronicles/{chronicleProjectId}/handoff
```

The body is UTF-8 JSON and contains exactly one top-level, camel-cased
`installationId` plus only the endpoint's domain fields. Duplicate or
case-variant installation identity properties fail closed. An `accessToken`
property at any nesting level is rejected.

## V2 install-link bootstrap

Before a bearer exists, new Android clients poll the separately authenticated
bootstrap route:

```text
POST /api/v2/install-linking/callbacks/poll
```

Its token-free JSON body contains `operationId`, `installationId`, `headId`,
`applicationVersion`, `channelId`, `platform`, `architecture`, `publicKey`,
`issuedAtUnixSeconds`, `nonce`, `signature`, and optional `hostLabel`. The
signature is RSA PKCS#1/SHA-256 over these UTF-8 LF-only lines with no trailing
LF:

```text
chummer.install-link.remote-callback.v2
POST
/api/v2/install-linking/callbacks/poll
<operationId>
<installationId>
<headId>
<applicationVersion>
<channelId>
<platform>
<architecture>
<issued Unix seconds as invariant decimal>
<nonce>
<hostLabel or empty string>
```

The submitted base64 DER SubjectPublicKeyInfo is cryptographically bound by
being the key that must verify the signature and by exact equality with the
account-approved callback key and install identity. The optional `hostLabel` is
signed device-supplied display metadata; it is not browser-approved identity.
Query strings are rejected.
`operationId` is required and is the canonical unpadded base64url encoding of
exactly 24 random bytes (32 characters). It is included in the signed bootstrap
payload after the endpoint path. On success, JSON contains only
`{installation, grant, alreadyClaimed, operationId, grantTransport}` where
`grant` is safe metadata, the exact `operationId` is echoed, and
`grantTransport` is the stable value `android-linked-v2`. The issued secret and
grant ID use the same mandatory single response headers as refresh:

```text
Authorization: Bearer <issued installation access token>
X-Chummer-Grant: <issued grantId>
```

If that successful response is lost, the client retries the same stable
operation during the callback lifetime using the same `operationId` and
immutable install fields but a fresh timestamp, nonce, and signature. Every
retry proof is verified and its nonce is admitted through the durable replay
authority; reusing a proof envelope is rejected. The Hub returns the original
installation, grant metadata, grant ID, and bearer and does not mint a second
grant. Recovery is bound to the durable callback, original grant, transport,
owner, canonical device key, operation ID, and stable-operation digest. A
changed operation, body, key, installation, owner, expired/revoked callback, or
expired/revoked/replaced grant fails closed. Recovery receipts survive restart
and share the same PostgreSQL compare-and-swap snapshot as the grant.

## Required headers

```text
Authorization: Bearer <installation access token>
X-Chummer-App-Proof: chummer.android.packet.v2
X-Chummer-Installation: <installationId>
X-Chummer-Grant: <grantId>
X-Chummer-Packet-Key: <32 random bytes, unpadded base64url>
X-Chummer-Packet-Issued: <Unix seconds>
X-Chummer-Packet-Signature: <standard base64 RSA signature>
```

`X-Chummer-Installation` must exactly equal the JSON `installationId`.
`X-Chummer-Grant` is the non-secret grant identity returned by credential
exchange or the preceding refresh. The Hub resolves the bearer token, grant,
installation, active status, expiry, and stored installation public key as one
atomic authorization decision.

The packet timestamp must be within two minutes of Hub time. A packet key is
single-use for that grant within the acceptance window. Replay receipts are
stored as non-secret SHA-256 keys inside the encrypted InstallLinking durable
snapshot. They therefore survive process restart and participate in the same
PostgreSQL compare-and-swap authority when that shared authority is active.
The local-file authority already enforces its existing exclusive writer lease.
If replay receipt persistence or shared compare-and-swap fails, admission fails
closed with `503`; the request is never dispatched. Reuse returns `409`;
missing, malformed, substituted, expired, or incorrectly signed authority
returns `401` without echoing credentials.

## Canonical request proof

The signature input is UTF-8, consists of exactly eight LF-separated lines,
and has no trailing LF:

```text
chummer.android.packet.v2
<uppercase HTTP method>
<exact escaped Request.Path.Value, preserving case>
<installationId>
<grantId>
<issued Unix seconds as invariant decimal>
<packetKey exactly as sent>
sha256:<lowercase hex SHA-256 of the exact request-body bytes>
```

The client signs these bytes with the installation RSA key using RSASSA-PKCS1-
v1_5 and SHA-256. The Hub imports the stored public key as base64-encoded DER
SubjectPublicKeyInfo and accepts RSA key sizes from 2048 through 4096 bits.

The bearer secret, an access-token digest, and Play Integrity material are not
members of this proof payload. Grant substitution is prevented by the signed
grant ID and by resolving that grant ID and bearer token to the same active
installation. Endpoint substitution is prevented by the signed exact path.

## Refresh response

The refresh request is authenticated with the old bearer/grant and may update
the install identity fields included in its signed body. A successful refresh
atomically records the old grant as revoked, issues and persists the replacement,
and returns safe installation/grant metadata plus the exact echoed `operationId`
and `grantTransport: "android-linked-v2"` in JSON. The old bearer is invalid for
both v2 and the retained legacy v1 resolver after commit. The newly issued
secret is delivered only in the response header:

```text
Authorization: Bearer <new installation access token>
X-Chummer-Grant: <new grantId>
```

Refresh JSON also requires a 32-character canonical `operationId`. If the
response is lost, the client may retry for 10 minutes with the exact old bearer,
source grant, operation ID, and byte-identical stored request body, but a fresh
timestamp, packet key, and signature. The Hub verifies the fresh proof with the
same device key and admits its packet key through the ordinary durable replay
authority before returning the same replacement bearer and grant metadata. It
never rotates a second time. Reusing the original proof envelope is a replay
conflict. Any bearer, operation, body, installation, key, or owner change uses
the normal denial path, as does an expired receipt or a replacement that is no
longer the active current v2 grant. The recovery mapping is committed in the
same durable write/CAS as the rotation, and its source and replacement grants
are pinned during retention for the entire recovery window.

The response JSON has no access-token member. All v2 responses are private,
`no-store`, `no-cache`, `no-referrer`, and `nosniff`. Admission logs contain
only a bounded reason code, numeric status, and a fixed surface label; request
bodies, bearer values, signatures, installation IDs, and dynamic route values
are not logged.

## Version boundary

Every newly issued grant has durable transport authority: `legacy-v1` or
`android-linked-v2`. V1 proof values and grants cannot authorize v2, and v2
grants are rejected by the legacy JSON-token resolvers, including legacy grant
refresh/revoke. Refresh preserves the source transport. The v2 middleware does
not reinterpret a v1 body token as bearer authority, and it does not intercept
the legacy v1 routes. The v2 bootstrap has its own scheme and endpoint binding,
so a legacy proof cannot authorize it.

Snapshots created before transport authority existed have no marker. Those
unmarked grants migrate only as `legacy-v1`, preserving deployed Preview 10
clients without guessing v2 authority from mutable installation fields. The old
record shape cannot distinguish a legacy grant from a v2 grant. Consequently,
this compatibility migration is safe only when transport authority ships before
v2 grant issuance; if an earlier v2 build issued grants, those ambiguous grants
must be invalidated at rollout and the affected devices must relink. Every grant
issued after this change is explicitly classified, and an explicitly classified
v2 grant cannot be downgraded through v1. The v1 callback and linked-account
routes remain available only for Preview 10 compatibility.

The operation-ID proof format and the matching Android client must roll out as
one compatibility boundary. An older Hub does not include `operationId` in the
bootstrap signature, while this Hub requires it for bootstrap and refresh.
Receipts written by the immediately preceding exact-proof retry implementation
remain readable but cannot be upgraded into a stable operation: an Android
device that lost such an in-flight response must start a fresh link. Existing
successfully received grants retain their transport authority and continue to
work; only bootstrap/refresh requests need the new operation field.
