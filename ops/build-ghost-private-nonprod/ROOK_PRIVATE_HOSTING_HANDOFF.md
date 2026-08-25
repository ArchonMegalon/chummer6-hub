# Private Rook hosting handoff

This handoff covers the fail-closed source posture built on the runtime merged
through Hub PR #237. It
does not record a deployment, provider readback, public route, or live-support
capability.

## Source boundary

The private lane keeps two different access paths separate:

* The provider-neutral v2 Build Ghost tool remains the externally bounded
  path. A signed-in owner receives one opaque, five-minute packet key from
  Presentation; the same owner may dispatch it once through the optional
  Cloudflare Access edge. The edge retains only owner/key digests and cannot
  reach the Rook support, live-support, explain, or internal resolver routes.
* The Rook support projection is an internal Presentation-to-AI call using the
  existing distinct AI service token. The checked-in private Caddy and optional
  Cloudflare edge do not expose that internal API. The signed-in account page
  remains behind the normal Hub identity boundary and is not made public by
  this slice.

Do not widen the Access edge to proxy the account page or AI support endpoint.
A private signed-in web ingress, if required, must reuse the normal Hub session
authority and receive a separate route and cookie/security review.

## Deliberately active behavior

Only deterministic, Chummer-owned behavior is selected:

* `CHUMMER_BUILD_GHOST_AI_BASE_URL` points Presentation at the internal AI
  service name; the two containers receive the same AI service token.
* The default support projection identifies Rook and returns the fixed local
  text fallback.
* The existing owner-bound packet grant remains five-minute, one-use, and
  revocable when its workspace closes.
* The AI live-support journal uses a separate writable named volume at
  `/app/state/build-ghost-live-support`, a stable operator-held AES key, and the
  literal single-instance posture required by the store implementation.

The local canary now rejects the runtime unless the Rook projection is
`text-fallback`, the live provider list is empty, remote execution is disabled,
the encrypted store reports no topology blocker, and the original owner-bound
packet journey still passes.

## Deliberately blocked behavior

The Compose source pins these inputs to empty strings and does not allow an
ambient environment value to activate them:

* live-support capability receipt, receipt HMAC, and expected account,
  scenario, and avatar digests;
* Rook VidBoard media href, content digest, and persona-release registry;
* meeting broker URL and token; and
* Tough Tongue meeting-bot API key, scenario, and bot name.

`CHUMMER_BUILD_GHOST_LIVE_SUPPORT_REMOTE_EXECUTION_ENABLED` is a literal
`false`, in addition to the four existing literal-false Tough Tongue execution
and canary gates. Consequently Zoom, Teams, Tough Tongue, and provider-managed
avatar work cannot be attempted. No captions, lip sync, live-avatar readiness,
or VidBoard media availability is claimed. An approved pre-rendered clip needs
its separately reviewed registry entry, exact same-origin file, and byte digest
in a later change; absence continues safely as text.

## First rollout prerequisites

1. Use an authoritative Hub revision containing merged PR #237 (minimum source
   base `afcdeac94bea696ace40614d3c6aa57f20833b52`). This configuration names
   runtime contracts introduced there and must not be backported alone.
2. Use clean, isolated source trees and exact revisions for all six Compose
   build contexts. Do not build against a dirty canonical checkout.
3. Place one stable, canonical base64 encoding of exactly 32 random bytes in
   the operator's external secret authority. It must differ from the private
   tool and AI internal tokens. This repository neither creates nor stores it.
4. Start the full lane for the first transition. The bounded AI and
   Presentation update helpers intentionally recover the journal key only from
   an already running AI container; they fail closed rather than bootstrap or
   rotate it.
   The full-lane one-shot store initializer has no network, drops all
   capabilities except `CHOWN` and `FOWNER`, initializes only an empty volume,
   and rejects a link or nonempty volume with unexpected ownership/mode.
5. Keep one AI replica. The file journal plus process-local reservation gate is
   not a multi-replica lock service.
6. Keep the default loopback-only edge unless a separately reviewed Access
   application, tunnel network, and route handoff is authorized. The optional
   Access profile still does not expose the signed-in Rook page.

After a separately authorized rollout, run:

```sh
./ops/build-ghost-private-nonprod/run-local-canary.sh
```

Accept only a terminal receipt containing all of
`rook=text-fallback`, `live_support=disabled`, `store=private`, `gates=false`,
and the existing one-use/replay/revocation proof. This command does not call a
provider.

## Blocker map and stop conditions

The following runtime blocker families are expected or actionable:

| Runtime observation | Meaning | Operator action |
| --- | --- | --- |
| `live-support-remote-execution-disabled-by-default` | Intended source posture | Keep it; this is not an incident. |
| capability, meeting-broker, or meeting-bot configuration blocker | Intended live-provider posture | Keep provider inputs empty in this lane. |
| Rook VidBoard release, href, or digest blocker | No approved local clip is bound | Continue with deterministic text; do not invent a media receipt. |
| `live-support-session-store-path-*` | Store path is absent or invalid | Stop; verify the exact named-volume mount and absolute path. |
| `live-support-session-store-directory-*` | Directory is missing or a link | Stop; rebuild from the reviewed image/volume topology. |
| `live-support-session-store-permissions-*` | Owner-only mode cannot be proved | Stop; require exact mode 0700 owned by the AI runtime UID. |
| `live-support-session-store-key-*` | Key is absent or does not decode to 32 bytes | Stop; correct the external secret authority without printing it. |
| `live-support-single-instance-posture-unverified` | Safe reservation topology is not selected | Stop; restore literal `true` and one AI replica. |
| local canary `stage=rook-support-fallback` | Projection, provider, or store posture drifted | Stop; do not expose ingress or activate any provider. |

Do not rotate the journal key while open or retained sessions exist: old
records become intentionally unreadable and capacity reconciliation fails
closed. A key rotation needs a separate terminal-session inventory, retention
decision, rollback plan, and audited activation window.

## Remaining activation-only work

This source is ready to review, not ready to claim as hosted. Current runtime
activation still needs a reviewed deploy window, exact image/source-label
readback, successful local canary, and an authorized ingress decision. An
approved VidBoard asset is optional and absent; Zoom, Teams, and Tough Tongue
are intentionally out of scope. Their credentials, capability receipts,
canaries, quota evidence, and provider mutations must remain absent.
