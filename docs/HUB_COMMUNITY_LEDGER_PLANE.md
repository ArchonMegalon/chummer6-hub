# Hub Community And Ledger Plane

`chummer6-hub` now owns the reusable community sponsorship spine for Chummer6.

## Canonical split

- Identity subject and session truth stays in `Chummer.Run.Identity`.
- Product-level user, group, and sponsorship truth lives in `Chummer.Run.Api`.
- Product-level linked identities and channel links also live in `Chummer.Run.Api`.
- Sponsor-session receipt ingest and execution-side projections live in `Chummer.Run.AI`.
- Fleet remains the sponsored worker executor.
- EA remains the provider-aware telemetry substrate.

## Core concepts

- `principal`: the authenticated subject from the hosted identity boundary
- `user`: the product-level human account layered above raw principals
- `group`: a reusable social/authority container with `group_type`, `visibility`, and capability flags
- `membership`: the user's role inside a group
- `linked identity`: a provider-backed or verification-backed auth/recovery identity attached to a product user
- `channel link`: a user-approved messaging or companion channel bound to Hub policy
- `sponsor session`: a consented participation session that can open a temporary sponsored Fleet lane
- `entitlement`: a durable product right granted to a user or group

Email verification is identity hygiene, not a separate product pillar.
Google, Facebook, and Telegram are adapters around the Hub-owned account model.
EA remains the orchestrator brain behind official companion channels; channel adapters do not replace that brain.

## Three ledgers, not one

Hub keeps three distinct accounting layers:

- fact ledger: immutable contribution events and sponsor-session receipts
- reward journal: derived points, streaks, and badge-oriented score events
- entitlement journal: durable product rights such as flair, beta access, or GM-tool priority

Points and perks come from validated receipts after meaningful work. They do not come from merely linking an account or idling in device auth.

Receipt ingest requires both:

- `X-Fleet-Receipt-Signature` on the inbound request
- a matching `signed_by_fleet` payload field computed with `FLEET_RECEIPT_SIGNING_SECRET`

Hub rejects unsigned or mismatched receipts before they can mint rewards, badges, or entitlements.

## Current hosted surfaces

Community/account controllers in `Chummer.Run.Api`:

- `AccountsController`
- `GroupsController`
- `BoostCodesController`
- `BoostSessionsController`
- `LedgerController`
- `LeaderboardsController`
- `EntitlementsController`

Community services in `Chummer.Run.Api/Services/Community`:

- `AccountService`
- `GroupService`
- `BoostSessionService`
- `LedgerService`
- `RewardService`
- `EntitlementService`
- `LeaderboardService`
- `CommunityStore`
- `HubIdentityClient`
- `FleetReceiptVerifier`

Current durability posture:

* `CommunityStore` is now a durable local snapshot store, not a process-local demo dictionary.
* The snapshot path defaults to a local app/temp location and can be overridden with `CHUMMER_COMMUNITY_STORE_PATH`.
* This is the current hosted durability baseline for the community plane until a stronger database-backed store is justified.

AI-side receipt/projection surfaces in `Chummer.Run.AI`:

- `BoosterReceiptsController`
- `BoosterReceiptProjectionService`
- `BoosterReceiptVerifier`

## Boundary rules

- Hub owns canonical user/group/ledger/reward/entitlement truth.
- Caller-supplied `subjectId` values must match an active bearer-bound identity session before Hub will read or mutate private account, group, or sponsor-session state.
- Fleet may cache sponsor metadata for lane execution, but it is not the canonical community ledger.
- Git commits, Fleet telemetry files, and EA provider health are evidence sources, not the product reward ledger.
- Sponsored lanes never receive direct merge authority; `jury` still lands protected work.
- Boosting is the first public use case for a generic community/group/accounting platform, not a one-off booster-only schema.
- Public participation routes must resolve onto sponsor-session/community-ledger truth instead of keeping a parallel intent-only state model.
