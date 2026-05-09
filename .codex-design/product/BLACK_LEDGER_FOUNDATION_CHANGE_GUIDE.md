# BLACK LEDGER foundation change guide

## Purpose

This file lists the specific changes Chummer should make **now** if it wants to build BLACK LEDGER later without running into structural blockers.

The rule is simple:

> If the future world-state layer matters enough to shape today's architecture, its required foundations must be visible now rather than rediscovered after flagship surfaces harden.

## The biggest future blockers to avoid

### 1. Overloading the campaign contract family

Do **not** jam world-state concepts into `Chummer.Campaign.Contracts`.

Campaign truth and world truth are adjacent, but they are not the same thing.

Change now:
- reserve a future shared family named `Chummer.World.Contracts`
- keep campaign objects focused on runner dossier, crew, campaign, run, scene, objective, continuity, and recap
- let campaigns reference world objects later instead of owning them semantically

Why:
If campaign contracts absorb faction seats, district pressure, world ticks, and strategic projects too early, both the campaign workspace and the future world engine will become muddy.

### 2. Letting rule environments stay too narrow

The current rule-environment system already supports explicit package and amend truth. That is good enough to avoid the biggest blocker — but only if the system grows one step more flexible.

Change now:
- define a first-class path for **world-linked availability offers**
- define a first-class path for **scenario modifiers / threat tags**
- define a first-class path for **campaign package overlays** that remain visible and receipt-backed
- forbid hidden world-state mutation of build legality or runtime meaning

Why:
BLACK LEDGER will need to surface things like prototype ware, ritual pressure, district lockdown modifiers, and faction-specific opposition packages. If the only way to do that later is ad hoc hidden flags, the world layer will corrupt trust.

### 3. Under-modeling organizer and seat authority

The current campaign and community model already distinguishes user, GM, organizer, and generic group capability. That should be widened carefully now.

Change now:
- reserve capability semantics for `world_operator`, `season_operator`, and later `faction_seat`
- keep these as capability flags or role classes, not one-off hardcoded special cases
- separate `gm_curates_run` from `manager_controls_faction_seat`
- keep organizer authority distinct from faction-seat authority

Why:
If this is not explicit early, future seat control will collide with campaign ownership, and the world layer will become politically and semantically messy.

### 4. Keeping job packets too campaign-local

Today the mission/run model is campaign-centered. That is correct. But future world-driven jobs need a thin pre-campaign opportunity object.

Change now:
- create a clear semantic seam between a **job seed** and a **campaign run**
- allow the system to hold pre-run opportunity packets without pretending they are already canonical campaign runs
- keep campaign adoption of a packet explicit and approval-based

Why:
Without this seam, the world layer will either mutate campaigns too early or stay too detached to be useful.

### 5. Failing to reserve space in the workspace

The campaign workspace already answers “what changed for me?” That is the right center. It should learn one more category now: **world pressure**.

Change now:
- reserve a future projection area in the home cockpit and campaign workspace for:
  - district pressure
  - sponsor tension
  - available world-linked jobs
  - world consequence summaries
- keep that area compact and explain-first, not dashboard-noise-first

Why:
If flagship workspace surfaces harden without a place for world pressure, the later layer will either feel bolted on or will force a destructive redesign.

### 6. Letting support/control and world/control collapse together

The product-control plane is now real. Keep it separate.

Change now:
- codify that world-state truth is **not** part of `Chummer.Control.Contracts`
- allow world events to produce signal packets later, but never store world truth in the support/control plane
- keep GM resolution and organizer approvals separate from support-case closure semantics

Why:
The moment world consequences and support/decision packets merge into one mushy control plane, the operator model becomes harder to reason about.

### 7. Leaving replay/debrief semantics too weak

BLACK LEDGER wants runs to have durable consequences. That depends on stronger resolution semantics than “session happened.”

Change now:
- add room for a future `ResolutionReport` layer between a run and later campaign/world consequences
- keep this explicit, approval-aware, and linked to receipts, recap, and continuity
- do not let summaries or debrief tools mutate truth directly

Why:
Future world-state changes need a clean approved bridge from “a run concluded” to “the city now changed because of it.”

### 8. Treating publication as an afterthought

The future world layer becomes much more valuable when it emits artifacts.

Change now:
- reserve artifact families for:
  - city ticker
  - district heat snapshot
  - faction propaganda
  - mission briefing reel
  - season recap
- keep those families receipt-backed and approval-aware in Media Factory and Registry planning

Why:
If publication types are only invented after the world engine exists, the wow-factor path arrives too late and feels optional.

## Specific design changes to make now

### A. Add a horizon and explicit build path

Add:
- `products/chummer/horizons/black-ledger.md`
- one root-registry entry in `HORIZON_REGISTRY.yaml`

Build path:
- `horizon`
- `bounded_research`
- `gm_only_world_engine`
- `shared_city_pilot`
- `human_faction_seats`
- `season_ops`
- `public_media_and_creator_integration`

### B. Reserve the future contract family now

Add to design canon:
- a placeholder mention of `Chummer.World.Contracts` in `CONTRACT_SETS.yaml`
- status should remain future / not-promoted until the horizon advances
- define early subfamilies:
  - `world_frame_vnext`
  - `mission_market_vnext`
  - `resolution_report_vnext`

### C. Extend campaign and journey canon without widening release scope

Update:
- `CAMPAIGN_SPINE_AND_CREW_MODEL.md` to mention world-linked references as future adjacent objects, not campaign-owned truth
- `CAMPAIGN_WORKSPACE_AND_DEVICE_ROLES.md` to reserve world-pressure and mission-market projection areas
- `USER_JOURNEYS.md` to note that future Run and Publish journeys may compile from mission-market packets and city-state summaries

Do **not** yet make any of this release-blocking.

### D. Extend rule-environment canon carefully

Update:
- `RULE_ENVIRONMENT_AND_AMEND_SYSTEM.md`

Reserve:
- `WorldOffer`
- `ThreatTag`
- `ScenarioModifier`
- `CampaignOverlayPackage`

Rule:
all world-linked mechanics must surface as explicit environment-linked or activation-linked facts.

### E. Extend role and community vocabulary

Update:
- `COMMUNITY_SPONSORSHIP_BACKLOG.md` or successor community docs
- `CAMPAIGN_AUTHORITY_AND_PERMISSIONS.md`

Reserve:
- `world_operator`
- `season_operator`
- `faction_seat`
- `campaign_consumer_of_world_packet`

Rule:
generic capability flags first, not hardcoded bespoke identity classes.

### F. Add future-proof telemetry and metrics seams

Reserve in product metrics / telemetry:
- job packet opened
- job packet adopted into campaign
- run completed from job packet
- world consequence viewed
- district pressure acknowledged
- season recap opened

This should remain latent until the build path advances.

## The first bounded research target

The safest first implementation later is **GM-only world engine**.

Reason:
- no manager-player fairness problem yet
- no async PvP politics yet
- no global season dependence yet
- immediate value to campaigns and artifacts
- validates whether the world layer actually improves mission generation before it becomes a second game

## Release and governance rule

BLACK LEDGER must not enter flagship truth until all of the following are true:
- world-linked packets can be adopted into campaigns without semantic confusion
- world-linked offers and modifiers stay inspectable through receipts
- organizer / GM / seat authority is explicit and testable
- mission board proof exists in executable surfaces, not only in horizon prose
- artifact outputs from the world layer are approval-safe and provenance-safe

## Bottom line

If Chummer makes these changes now, BLACK LEDGER can grow later as a powerful world-state layer.

If it does not, the likely failure modes are:
- campaign contracts bloated with strategy semantics
- hidden rules mutations from “world state”
- GM authority and manager authority colliding
- mission packets faking campaign truth too early
- the city feeling like a gimmick instead of a memory-bearing system
