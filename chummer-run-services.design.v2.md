
# chummer-run-services.design.v2.md

Version: v2.0  
Status: authoritative design for Codex Instance C

## 1. Mission

`chummer.run-services` is the **clean-room hosted service and creative orchestration stack** behind `chummer.run`.

It owns:

- portal/auth/campaign/user roles
- Hub registry
- RulePack / RuleProfile / BuildKit / NPC / BuildIdea publication
- reviews, moderation, delisting, install history
- runtime-bundle delivery
- AI gateway and provider routing
- lore retrieval / vector search
- Chummer Coach
- GM Director / Spider
- Session relay and session memory services
- creative asset generation orchestration
- docs/help surfaces
- notifications and delivery channels

It does **not** own:

- core Shadowrun math
- XML parsing and legacy save upgrading
- RulePack compilation internals
- direct copies of GPL mechanics code

This repo is where **campaign operations, AI assistance, and creative artifacts** live.

No monetization is implemented now. All feature flags are capability flags only.

---

## 2. Product responsibilities

## 2.1 Hub and campaign OS features owned here

1. **Hub**
   - RulePack registry
   - RuleProfile registry
   - Character Templates / BuildKits
   - NPC Vault and Encounter Packs
   - BuildIdea library
   - reviews, ratings, install history, moderation
   - immutable artifact retention

2. **Chummer Coach**
   - grounded rules coaching
   - build advice
   - advancement planning
   - legwork assistance
   - debrief summaries

3. **GM Director / Spider**
   - observation ingest
   - two-tier trigger pipeline
   - lore-aware orientation
   - scene-bound suggestions
   - stale draft invalidation
   - DeliveryOutbox
   - interruption budget enforcement

4. **Creative Asset Factory**
   - Portrait Forge
   - Johnson's Briefcase
   - Sixth World News Network
   - Route Cinema
   - Shadowfeed
   - dossier/document rendering
   - NPC message/video assets

5. **Session Memory Engine**
   - transcript ingestion
   - recap drafts
   - unresolved thread extraction
   - timeline event drafts
   - relationship-change drafts
   - canonization workflow

6. **Docs Concierge**
   - API docs
   - user help
   - RulePack author docs
   - context-aware assistant grounded on docs and runtime facts

---

## 3. Core architecture principles

1. **Clean-room boundary**
   - no GPL mechanics implementation here

2. **Grounded before generative**
   - AI answers are grounded on RuntimeLock, Explain results, rule/profile metadata, and approved lore before general model reasoning

3. **Draft first**
   - all AI outputs begin as drafts unless an explicit autonomy policy allows automatic delivery

4. **Artifacts are immutable**
   - published RulePacks, RuleProfiles, BuildKits, NPCs, and runtime bundles are never hard-deleted once installed by users
   - they may be delisted, deprecated, or superseded only

5. **Media is cacheable and disposable**
   - heavy generated assets are versioned, TTL-bound, and stored off the app server

6. **Session state is event-only**
   - relay accepts immutable deltas only
   - no absolute tracker overwrite API

7. **Interruptions are budgeted**
   - the Spider serves the GM, not the other way around

---

## 4. Hosted subsystems

## 4.1 AI Gateway

Components:
- `AiGatewayService`
- `ProviderRouter`
- `PromptRegistry`
- `RetrievalService`
- `ConversationStore`
- `AiBudgetService`
- `EvaluationStore`

Provider policy:
- AI Magicx: primary for tool-calling and structured workflows
- 1min.AI: fallback / multimodal / lower-cost generation
- BrowserAct: API-less vendor adapter only, off the critical path
- ChatPlayground: eval and comparison environment only
- Prompting Systems: prompt template and persona prompt authoring support

## 4.2 Session and Spider

Components:
- `ObservationIngestService`
- `FastSignalDetector`
- `DirectorPolicyEngine`
- `PersonaMemoryRetriever`
- `DeliveryOutbox`
- `SessionLedgerService`
- `SessionRuntimeBundleService`

## 4.3 Hub

Components:
- `ProjectCatalogService`
- `PublicationService`
- `ModerationService`
- `ReviewService`
- `InstallHistoryService`
- `RuntimeBundleCatalog`
- `NpcVaultService`
- `BuildIdeaService`

## 4.4 Asset factory

Components:
- `PortraitForgeService`
- `PacketFactoryService`
- `RouteCinemaService`
- `NewsNetworkService`
- `AssetLifecycleService`
- `PreviewThumbnailService`

## 4.5 Docs and support

Components:
- `DocumentationBridge`
- `RuntimeHelpService`
- `AuthorDocsService`

---

## 5. Concrete feature design

## 5.1 Chummer Coach

Coach persona:
- trusted decker contact
- sardonic, competent, paranoid
- on limitation/failure: “GOD is breathing down my neck, chummer”

Modes:
- Rules Referee
- Build Coach
- Advancement Planner
- Legwork Assistant
- Debrief Scribe

The persona is flavor only. Truth comes from runtime and retrieval.

Every answer must attach:
- runtime fingerprint
- relevant pack/profile IDs
- confidence level
- evidence pointers
- whether it is safe to apply automatically (usually no)

## 5.2 Portrait Forge

Inputs:
- aesthetic digest from engine
- optional background story
- style family
- persona consistency references
- approved portrait anchor images

Outputs:
- draft portrait variants
- undercover variant
- damaged/post-run variant
- dossier headshot
- wanted-poster variant

Design rules:
- keep a `PersonaConsistencyRegistry`
- select one canonical portrait per entity
- store style tokens and prompt lineage
- cache aggressively
- expose reroll/approval history

Providers:
- 1min.AI and AI Magicx for image generation/prompt assistance
- Prompting Systems for style prompt templates
- PeekShot for thumbnails/previews

## 5.3 Johnson's Briefcase

Generate:
- mission briefs
- corp dossiers
- KE bulletins
- clinic reports
- invoices and shipping manifests
- fake internal memos

Pipeline:
1. gather structured seeds from engine and campaign
2. LLM drafts text
3. HTML template fill
4. MarkupGo render to PDF/image
5. PeekShot generate thumbnail
6. approval gate
7. attach to campaign / message / export

## 5.4 GOD Threat Tracker and Spider Feed

Track:
- matrix heat
- law-enforcement heat
- corp attention
- magical attention
- local district alertness

Spider Feed UX semantics:
- tactical cards, not chat
- scene-bound
- stale if context shifts
- one-tap actions
- mute / snooze / pin
- autonomy ladder

Autonomy levels:
- Off
- Low
- Tactical
- Narrative
- High

`InterruptionBudget` is a campaign/session setting and is mandatory.

## 5.5 Sixth World News Network

Outputs:
- short text recap
- longer “last time on” recap
- in-universe news bulletin
- optional video bulletin
- fallout summary

Pipeline:
1. transcript + session ledger + approved notes
2. extract facts
3. draft summary
4. rewrite in in-universe tone
5. optional Mootion render
6. approval
7. delivery to players / archive

Mootion Tier 3 constraints to design around:
- credit budget
- 32-scene/project limit
- 1080p
- multimodal input
- rerender cost on retries

Therefore:
- scripts must be short and templated
- maintain shot lists
- keep result TTL unless pinned
- cache generated outputs

## 5.6 Route Cinema

Use AvoMap for:
- travel route clips
- smuggling paths
- exfil paths
- campaign movement recaps

Pipeline:
1. derive route points from session/campaign data
2. generate route payload
3. render video
4. store artifact with preview and metadata
5. optional narration overlay later

## 5.7 Shadowfeed

A diegetic world-state output:
- corp headlines
- rumor feed
- police chatter
- gang whispers
- matrix posts
- magical weirdness bulletin

It must be grounded on approved campaign facts and local lore retrieval.

## 5.8 NPC Persona Studio

Every recurring NPC may own:
- canonical portrait/video references
- tone profile
- slang profile
- affiliation
- relationship state by player
- spoiler boundary
- channel permissions
- approval policy
- lore memory bank
- delivery constraints

This is a first-class registry artifact, not prompt glue.

## 5.9 Session Memory Engine

Input:
- text notes
- session ledger
- optional audio transcript
- player/GM messages

Output drafts:
- recap
- unresolved hooks
- timeline events
- relationship changes
- character history snippets
- faction heat changes
- canon write proposals

All write-backs require approval.

## 5.10 Lore Lens / fluff-aware orientation

Support localized fluff-aware play by ingesting lore documents into a vector store.

Every lore chunk must carry:
- source
- jurisdiction / district / region
- topic tags
- campaign scope
- pack/profile linkage

The Director uses these only in the Orient phase of OODA, never as authoritative mechanics.

---

## 6. Two-tier live ingestion

Do not send every transcript chunk to a large model.

Use:

### Tier 1 — fast cheap detector
Detect:
- registered NPC names
- district/location names
- keywords like Edge, GOD, Overwatch, alarm, drone, fireball
- obvious scene-shift markers

### Tier 2 — deep context reasoning
Only when Tier 1 triggers:
- gather preceding context window
- retrieve persona memory and lore chunks
- call DirectorPolicyEngine

This saves tokens and reduces false positives.

---

## 7. Persona memory retrieval

Never load an entire NPC dossier into the prompt.

Split memory into:
- static persona card
- structured relationship state
- episodic memory
- hidden plot memory

At inference time:
- vectorize current observation
- retrieve top relevant persona memories
- inject only those memories plus hard rules

---

## 8. DeliveryOutbox and stale message handling

Every draft message or asset suggestion must carry:
- scene ID
- scene revision
- generated-at timestamp
- TTL
- invalidation signals
- autonomy mode
- approval state

If the scene changes, old drafts must become `stale` automatically and not be sent accidentally.

---

## 9. Session sync design

The relay accepts canonical `SessionEventEnvelope` deltas.

Examples:
- spend edge
- take damage
- reload ammo
- effect applied
- pin updated

Server behavior:
- merge event streams
- recalculate state
- return projection
- preserve history

No absolute tracker state writes.

For local-first clients, the server and client must converge from the event log, not from overwritten snapshots.

---

## 10. Localization and explanation use

Run Services must never invent local-language rule reasons when the engine has already provided localization keys.

The AI layer may summarize for convenience, but every rule explanation shown as authoritative must preserve the engine key lineage and evidence.

---

## 11. Asset lifecycle and storage

Heavy media is dangerous if handled naively.

Required design:

- active asset store: zero-egress object storage (for example Cloudflare R2)
- app/API servers return JSON and signed asset URLs, not large blobs
- portraits and small images: long cache
- recap videos and large assets: TTL default 30 days unless pinned
- client PWA caches portraits aggressively
- metadata DB records lifecycle, approval state, and retention

No app server should become a media CDN.

---

## 12. Immutable Hub registry rule

Once a RulePack / RuleProfile / BuildKit / NPC pack / runtime bundle is:
- published
- installed by at least one active user
- referenced by an active RuntimeLock

it must never be hard-deleted.

Allowed states:
- active
- delisted
- deprecated
- superseded
- banned-but-retained

This prevents ghost dependencies and orphaned RuntimeLocks.

---

## 13. Relevant LTD integrations

Use immediately:

- **1min.AI**
  - multimodal generation
  - image generation
  - image-to-prompt
  - fallback reasoning

- **AI Magicx**
  - primary structured/tool-calling provider
  - usage analytics and limits

- **Prompting Systems**
  - style packs
  - persona prompt compiler
  - image/video/story prompt templates

- **ChatPlayground**
  - eval lab only

- **BrowserAct** (highest tier)
  - UI-only vendor automation fallback
  - never on critical hot path

- **ApproveThis**
  - canon approvals
  - publish approvals
  - dossier/recap approvals
  - NPC message approvals

- **Documentation.AI**
  - docs and author portal
  - embedded help assistant
  - OpenAPI docs

- **MarkupGo**
  - dossier PDFs/images
  - packet generation

- **PeekShot**
  - previews
  - thumbnails
  - share cards

- **Mootion Tier 3**
  - recap/news/NPC video rendering
  - use sparingly with templates and cache

- **AvoMap**
  - route videos

- **MetaSurvey**
  - feature feedback
  - curation feedback
  - recap quality surveys

- **Teable**
  - moderation dashboard
  - curation board
  - GM ops projection board

- **Paperguide**
  - internal research and cited synthesis

- **Internxt**
  - cold archive only, not hot path

### Transcription recommendation

Do not wait on a perfect LTD to proceed.

Implement `ITranscriptionProvider` now with:
1. local/open provider adapter (`faster-whisper` or `WhisperX`)
2. optional external provider adapter later
3. transcript confidence and hallucination warnings
4. approval path before canon writes

If you want a buy-now LTD, `Unmixr AI` is the strongest current fallback fit.

---

## 14. No monetization now

All capability flags remain feature flags only.

Allowed now:
- internal quotas
- admin limits
- per-user safety budgets
- provider budget routing

Not allowed now:
- payment walls
- plan-based user locks
- hidden premium-only business logic

Design so future monetization is possible, but do not couple core features to billing.

---

## 15. First milestones for this repo

### Milestone C1 — Hub persistence and immutability
Deliver:
- registry tables
- delist/deprecate states
- no hard delete after install
Exit:
- runtime references never orphan

### Milestone C2 — AI gateway and prompt lab
Deliver:
- provider routing
- prompt registry
- eval harness
Exit:
- no feature calls providers directly

### Milestone C3 — Portrait Forge + packet factory
Deliver:
- artifact job pipeline
- approval flow
- cache + TTL
Exit:
- portraits and dossiers can be generated/reviewed without blocking the app

### Milestone C4 — Session Memory Engine
Deliver:
- transcription seam
- recap drafts
- timeline draft generation
Exit:
- approved recaps can write back to canon artifacts

### Milestone C5 — Spider Feed and OODA
Deliver:
- two-tier ingestion
- interruption budget
- stale draft invalidation
Exit:
- GM sees tactical cards instead of spam

### Milestone C6 — Lore Lens and persona retrieval
Deliver:
- lore ingestion/vectorization
- persona memory retrieval
Exit:
- Director outputs location- and NPC-aware guidance

### Milestone C7 — News/route/media suite
Deliver:
- News Network
- Route Cinema
- NPC video message jobs
Exit:
- campaign can generate approved recap and travel media

---

## 16. What Codex Instance C should do first

1. define immutable artifact and publication state models
2. implement `ITranscriptionProvider`
3. build AI Gateway and prompt registry
4. implement asset lifecycle service with TTL and zero-egress storage
5. build Portrait Forge and Johnson's Briefcase first
6. add two-tier Spider ingestion and interruption budgets
7. add Session Memory Engine and lore-aware retrieval
