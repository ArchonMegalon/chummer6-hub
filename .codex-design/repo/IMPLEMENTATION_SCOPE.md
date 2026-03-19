# Hub implementation scope

## Mission

`chummer6-hub` owns hosted orchestration plus the community/accounting control plane for Chummer6.

## Owns

* hosted orchestration and relay seams
* identity, approvals, memory, and delivery on the hosted side
* principal-to-user mapping and user-profile truth
* linked identities, verified-email hygiene, and social/channel adapter policy
* generic groups, memberships, join codes, and boost codes
* sponsorship / participation UX for Fleet premium burst lanes
* fact ledger, reward journal, and entitlement journal for community participation
* leaderboards, quests, badges, and community-side entitlement views
* the `chummer.run` public landing, proof shelf, public status, and signed-in home overlays
* play API aggregation and hosted session coordination
* orchestration-side Coach/Spider/Director surfaces
* hosted external-integration routing that is not render-only media execution

## Must not own

* engine or reducer truth
* player/GM/mobile shell UX
* shared UI-kit primitives
* long-term registry persistence ownership after the registry split
* long-term render execution ownership after the media-factory split
* raw participant Codex/OpenAI auth caches or device-auth secrets
* provider-credit accounting or provider-secret storage
* Fleet worker execution or landing authority

## Package boundary

Canonical hosted package plane:

* `Chummer.Play.Contracts`
* `Chummer.Run.Contracts`

Mixed contract planes are temporary debt, not acceptable end state.

## Boundary truth

Closing `A2`, `A3`, `C0`, `C1`, and `C2` required physical shrinkage, not only correct README wording.

The hub boundary is considered clean when:

* registry persistence authority is visibly owned by `chummer6-hub-registry`
* render-only media execution is visibly owned by `chummer6-media-factory`
* hub no longer reads like the hidden super-repo for every hosted concern
* active worklists highlight hosted implementation work instead of reconciliation churn

## Current reality

The mission statement and the repo body are much closer now.
Registry and media execution ownership are physically out of this repo.

The remaining work is future product depth and physical cleanup, not pretending hub still owns every hosted surface or still lacks authority proof.
Participation UX for premium burst lanes belongs here, but the resulting Codex auth cache stays lane-local on Fleet rather than being stored in hub identity or hub databases.

The first-class sponsor/consent/device-auth/lane/receipt lifecycle is defined centrally in `products/chummer/PARTICIPATION_AND_BOOSTER_WORKFLOW.md`.
The first-class linked-identity and channel-linking posture is defined centrally in `products/chummer/IDENTITY_AND_CHANNEL_LINKING_MODEL.md`.

## Sequencing rule

Do not treat boost codes or sponsored premium lanes as the first-class product.

Build order for the next serious Hub wave:

1. user accounts and profiles
2. generic groups, memberships, and join codes
3. fact ledger, reward journal, and entitlement journal
4. participation intent/session UX
5. Fleet receipt ingest and sponsor-session projections
6. leaderboards, badges, quests, and entitlement-backed perks

New booster-facing UX must not outrun that shared backbone.
The point is to make boosting the first public use case of a reusable community platform, not a one-off side feature.

## Community modeling rule

Canonical Hub concepts:

* principal: authenticated identity subject/session
* user: product-level human account
* group: reusable social / authority container with `group_type`, `visibility`, `capabilities`, and policy
* membership: user-to-group role relation
* entitlement: durable user or group product right
* sponsor session: bounded premium-burst sponsorship lifecycle

User accounts must not collapse into raw identity subjects, and group types must stay generic enough for `booster`, `campaign`, `gm_circle`, `creator_team`, `guild`, and future org-like surfaces.

Linked identities and linked channels are separate records:

* identity links cover email hygiene, social auth bootstrap, and recovery posture
* channel links cover official bot routing, notifications, and future advanced bot integrations

Telegram may appear in both planes, but it does not become the account core or a replacement for Hub-owned permissions.
EA remains the orchestration brain behind official companion channels.

The generic group system exists so later GM and campaign tooling can reuse the same account, role, and entitlement substrate rather than introducing a second social/authority model.

## Ledger rule

Hub keeps three ledgers:

1. fact ledger for immutable receipts and raw events
2. reward journal for points, badges, quests, and leaderboard scoring
3. entitlement journal for durable product-right grants and revocations

Do not fold these into one table or one DTO family.

Rewards must be derived from validated Fleet contribution receipts, not from merely redeeming a code or completing device auth.

## UI host rule

`Chummer.Run.Api` should host the first real community UI surface for:

* the public landing page and signed-in home shell
* account/profile management
* groups and memberships
* boost-code redemption
* participation consent and sponsor-session status
* leaderboards, rewards, and entitlements

That initial product shell can be server-rendered and thin, but it must exist here before Fleet grows more booster-specific product behavior.

## Fleet boundary handoff

Hub owns:

* participation intent creation
* consent UX
* user/group/ledger truth
* reward and entitlement derivation

Fleet owns:

* lane creation
* device-auth execution on the worker host
* worker lifecycle
* signed contribution receipts

Hub must not execute Codex auth directly, and Fleet must not become the canonical community ledger.
