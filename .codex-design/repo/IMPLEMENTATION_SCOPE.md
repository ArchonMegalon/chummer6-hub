# Hub implementation scope

## Mission

`chummer6-hub` owns hosted orchestration plus the community/accounting control plane for Chummer6.

## Owns

* hosted orchestration and relay seams
* identity, approvals, memory, and delivery on the hosted side
* principal-to-user mapping and user-profile truth
* generic groups, memberships, join codes, and boost codes
* sponsorship / participation UX for Fleet premium burst lanes
* fact ledger, reward journal, and entitlement journal for community participation
* leaderboards, quests, badges, and community-side entitlement views
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

## Community modeling rule

Canonical Hub concepts:

* principal: authenticated identity subject/session
* user: product-level human account
* group: reusable social / authority container with `group_type`, `visibility`, `capabilities`, and policy
* membership: user-to-group role relation
* entitlement: durable user or group product right
* sponsor session: bounded premium-burst sponsorship lifecycle

User accounts must not collapse into raw identity subjects, and group types must stay generic enough for `booster`, `campaign`, `gm_circle`, `creator_team`, `guild`, and future org-like surfaces.

## Ledger rule

Hub keeps three ledgers:

1. fact ledger for immutable receipts and raw events
2. reward journal for points, badges, quests, and leaderboard scoring
3. entitlement journal for durable product-right grants and revocations

Do not fold these into one table or one DTO family.
