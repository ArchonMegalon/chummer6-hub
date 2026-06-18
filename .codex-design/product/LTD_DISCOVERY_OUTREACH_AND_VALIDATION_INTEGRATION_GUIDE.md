# LTD Discovery, Outreach, and Validation Integration Guide

**Product:** Chummer 6 / SR Campaign OS  
**Primary repo:** `chummer6-design`  
**Status:** Proposal / implementation guide  
**Prepared for:** Chummer dev, Hub, Fleet, EA, Media Factory, and Product Governor teams  
**Newly purchased capabilities assumed:** `Icanpreneur` Tier 3, `GetNextStep.io` Tier 5, `Signitic` Tier 4, `Taja` Tier 4, `FacePop` Tier 5, `vidBoard` Tier 5, `Lunacal` highest tier, `Deftform`, `Subscribr.ai` Tier 7, plus the existing EA LTD inventory.

## 1. Executive summary

The Chummer LTD stack should not be treated as a pile of random SaaS tools.
It should become a governed product-learning and artifact-production system.

The highest-value use is:

> Recruit the right users, interview them about real table pain, convert the findings into typed discovery packets, route those packets through the Product Governor, then generate visible proof and follow-up loops without letting any LTD become Chummer truth.

The first flagship use case is KARMA FORGE house-rule discovery: learn what house rules GMs, players, creators, organizers, and Chummer5a veterans actually need Chummer to support before implementing rule-environment and amend-package features at scale.

Secondary use cases:

* GM Companion persona validation
* BLACK LEDGER faction / world-state validation
* TABLE PULSE LIVE and TABLE PULSE AFTERMATH validation
* creator publication and artifact-workflow validation
* public launch messaging and onboarding validation

## 2. Core rule

External tools may recruit, interview, assist, route, render, summarize, schedule, project, or measure.

External tools must not own:

* rules truth
* support truth
* campaign truth
* world truth
* release truth
* install truth
* publication truth
* approval truth
* design canon
* pricing or product-strategy truth

Every meaningful result that enters Chummer must become a Chummer-owned receipt, packet, issue, backlog candidate, or decision record.

## 3. Tool role map

### Icanpreneur

Primary role: adaptive discovery interview and validation lane.

Allowed:

* AI-led or AI-assisted interviews
* interview scripts for specific user types
* analysis of patterns across interviews
* buyer/user persona updates
* positioning and concept validation
* GTM-message exploration for risky product concepts

Forbidden:

* direct rule-package generation
* direct implementation priority decisions
* canon updates without Product Governor / design approval
* copyrighted book-text capture as raw source
* becoming the system of record for feature requests

Detailed posture lives in [ICANPRENEUR_DISCOVERY_AND_VALIDATION_LANE.md](/docker/chummercomplete/chummer6-design/products/chummer/ICANPRENEUR_DISCOVERY_AND_VALIDATION_LANE.md).

### FacePop

Primary role: bounded public concierge and recruitment front.

Allowed:

* public low-risk pages only
* concept intro videos
* branching CTA trees
* routing to Deftform, Icanpreneur, Lunacal, Hub pages, or public artifact pages
* moderated testimonial capture

Forbidden:

* desktop/mobile runtime integration
* authenticated workspace truth
* support-case truth
* install/claim/update truth
* campaign truth

### Deftform

Primary role: structured pre-screen and intake.

Allowed:

* pre-screen forms
* role / edition / table-type classification
* safe example upload where policy allows
* follow-up routing
* consent capture

Forbidden:

* canonical feature backlog
* rule truth
* support truth

### Lunacal

Primary role: human follow-up interview and clinic scheduling.

Allowed:

* GM follow-up calls
* creator clinics
* rule-pack review sessions
* organizer / BLACK LEDGER pilot calls
* setup / onboarding calls

Forbidden:

* support-case truth
* campaign truth
* final approval truth

### NextStep

Primary role: operator process execution layer.

Allowed:

* research sprint SOPs
* BLACK LEDGER world-tick procedures
* media artifact publication processes
* release checklists
* localization gates
* review and closeout steps

Forbidden:

* canonical process truth without mirrored registry or canon
* support truth
* campaign/world truth
* design truth

### Signitic

Primary role: passive outreach and signature-campaign projection lane.

Allowed:

* public recruitment CTAs
* release campaigns
* KARMA FORGE discovery recruitment
* BLACK LEDGER and GM Companion validation recruitment
* creator program CTAs
* A/B signature banners

Forbidden:

* product notifications of record
* support-case notifications of record
* world/campaign truth
* canonical analytics interpretation

### Taja

Primary role: approved media repurposing and distribution.

Allowed:

* repurposing approved vidBoard videos
* city ticker clips
* release snippets
* campaign primer excerpts
* creator or publisher promo cuts

Forbidden:

* creating unapproved claims
* becoming artifact truth
* posting without publication approval

### vidBoard

Primary role: polished presenter-video lane.

Allowed:

* concept videos for discovery recruitment
* campaign primers
* mission briefings
* release explainers
* support-closure explainers
* KARMA FORGE concept explainers

Forbidden:

* live runtime companion truth
* rules truth
* support truth
* unapproved public claims

### MetaSurvey

Primary role: quantitative follow-up after interviews.

Allowed:

* rank candidate features
* validate language after interview synthesis
* collect broad sentiment after a concept sprint

Forbidden:

* replacing qualitative interviews for complex rule-governance needs
* owning direct backlog priority

## 4. First flagship workflow: KARMA FORGE house-rule discovery

### Product risk

KARMA FORGE is not just an engineering feature.
It changes table trust.

Representative demand categories:

* custom gear availability
* alternate chargen methods
* advancement variants
* simplified matrix rules
* Edge-economy variants
* custom cyberware / spells / qualities
* campaign-scoped unlocks
* faction-linked BLACK LEDGER rewards
* Chummer5a custom-data import parity

### Discovery goal

Find the actual house-rule demand behind user wording.

Example:

> “Let me override gear availability.”

May actually mean:

> “Our street-level campaign needs a visible campaign-scoped availability overlay with build-impact preview, player-visible receipts, and later unlocks from run outcomes.”

### Public recruitment flow

1. FacePop prompt on `/karma-forge`, `/roadmap`, `/downloads`, or `/now`.
2. Deftform pre-screen captures role, edition, table type, rule category, severity, and current workaround.
3. Icanpreneur runs adaptive interviews.
4. Lunacal handles high-signal follow-up calls.
5. MetaSurvey validates clustered findings.
6. Product Governor converts clusters into KARMA FORGE candidates, rejections, or deferred research.

Detailed workflow lives in [KARMA_FORGE_DISCOVERY_AND_HOUSE_RULE_INTAKE.md](/docker/chummercomplete/chummer6-design/products/chummer/KARMA_FORGE_DISCOVERY_AND_HOUSE_RULE_INTAKE.md).

## 5. Canonical output rule

Every meaningful interview result must normalize into a Chummer-owned packet.
The canonical packet family for KARMA FORGE is `HouseRuleDemandPacket`.

The machine-readable track registry lives in [HOUSE_RULE_DISCOVERY_REGISTRY.yaml](/docker/chummercomplete/chummer6-design/products/chummer/HOUSE_RULE_DISCOVERY_REGISTRY.yaml).

## 6. Product Governor classification

Discovery output must land in one of these routes:

* `reject`
* `document_only`
* `preset_candidate`
* `amend_package_candidate`
* `campaign_overlay_candidate`
* `world_offer_candidate`
* `scenario_modifier_candidate`
* `core_ruleset_gap`
* `legacy_import_candidate`
* `research_more`

## 7. Required design surfaces

This guide depends on and now introduces these canonical files:

* [ICANPRENEUR_DISCOVERY_AND_VALIDATION_LANE.md](/docker/chummercomplete/chummer6-design/products/chummer/ICANPRENEUR_DISCOVERY_AND_VALIDATION_LANE.md)
* [KARMA_FORGE_DISCOVERY_AND_HOUSE_RULE_INTAKE.md](/docker/chummercomplete/chummer6-design/products/chummer/KARMA_FORGE_DISCOVERY_AND_HOUSE_RULE_INTAKE.md)
* [HOUSE_RULE_DISCOVERY_REGISTRY.yaml](/docker/chummercomplete/chummer6-design/products/chummer/HOUSE_RULE_DISCOVERY_REGISTRY.yaml)

It also requires the following canon to stay aligned:

* [LTD_CAPABILITY_MAP.md](/docker/chummercomplete/chummer6-design/products/chummer/LTD_CAPABILITY_MAP.md)
* [EXTERNAL_TOOLS_PLANE.md](/docker/chummercomplete/chummer6-design/products/chummer/EXTERNAL_TOOLS_PLANE.md)
* [horizons/karma-forge.md](/docker/chummercomplete/chummer6-design/products/chummer/horizons/karma-forge.md)
* [HORIZON_REGISTRY.yaml](/docker/chummercomplete/chummer6-design/products/chummer/HORIZON_REGISTRY.yaml)

## 8. Privacy, consent, and IP rules

### Consent

Every participant must know:

* what is being collected
* why it is being collected
* whether it may inform Chummer design
* whether quotes may be used
* how to request removal or anonymization

### Copyright and rulebook content

Allowed:

* descriptions in the respondent’s own words
* source/book/page references where lawful and necessary
* examples of their own house-rule wording
* Chummer5a custom-data examples after provenance review

Forbidden:

* raw sourcebook-text capture
* asking Icanpreneur to summarize pasted copyrighted passages
* embedding rulebook text into public discovery outputs

### Data minimization

Collect only what the discovery lane needs:

* user role
* edition
* table type
* rule need
* current workaround
* consent status
* follow-up permission

## 9. Success metrics and quality gates

First-sprint directional targets:

* `30` interviews completed
* `20` demand packets created
* `3` clusters with five or more signals
* `2` candidates promoted to design
* `5` candidates rejected with explicit reasons

A house-rule candidate is not ready for implementation until:

* at least one GM need is clear
* player trust impact is known
* rule-environment mapping is identified
* portability / restore behavior is defined
* rollback and activation-receipt behavior is defined
* copyright / provenance risk is cleared
* Product Governor has assigned a route

## 10. First 30-day plan

### Week 1

* add the design docs and registry
* add the new tool lanes to the LTD map and external-tools plane
* define the Deftform pre-screen
* create Icanpreneur projects for KARMA FORGE, GM Companion, BLACK LEDGER, TABLE PULSE LIVE, TABLE PULSE AFTERMATH, and creator publishing
* create the NextStep discovery sprint template
* create the Signitic recruitment campaign
* draft the FacePop public concierge flow

### Week 2

* publish the KARMA FORGE recruitment surface
* launch the FacePop prompt
* add the Signitic banner
* run the first interview cohort
* book high-signal Lunacal follow-ups

### Week 3

* cluster findings with EA
* draft the first `HouseRuleDemandPacket` set
* run MetaSurvey ranking of the top clusters
* classify candidates in Product Governor

### Week 4

* promote one or two candidates into design work
* reject or defer others with reasons
* create the first prototype spec for a governed amend-package or campaign-overlay candidate
* publish the discovery closeout
* create a vidBoard/Taja summary if the findings are public-safe

## 11. Anti-patterns

Do not:

* ask “what feature do you want?” and implement the loudest answer
* let interviews produce direct implementation tasks
* confuse house-rule demand with official-rules bugs
* treat synthetic or user-simulated interviews as validated demand
* allow hidden rule mutation
* capture raw copyrighted sourcebook text
* use Icanpreneur as the backlog system
* ship rule changes without activation receipts and rollback semantics

## 12. Developer handoff summary

The first implementation task is not engine work.

The first implementation task is a governed discovery pipeline:

1. public invitation
2. structured pre-screen
3. adaptive interview
4. normalized demand packet
5. EA clustering
6. Product Governor decision
7. KARMA FORGE candidate backlog
8. prototype only after trust and scope are known

## 13. Final recommendation

Use Icanpreneur aggressively for real discovery, especially around KARMA FORGE.

The point is not to ask users for feature requests.
The point is to learn:

* what house rules they actually use
* why they need them
* who needs to approve them
* what must be visible to players
* what must be portable across devices
* what should become reusable
* what should stay campaign-local
* what should never be implemented

That is the difference between a flexible rule editor and a trusted rule-governance system.
