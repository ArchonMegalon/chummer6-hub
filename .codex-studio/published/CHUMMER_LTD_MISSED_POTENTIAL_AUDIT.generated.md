# Chummer.run LTD Missed-Potential Audit

Date: 2026-05-07  
Scope: `chummer.run-services` against `/docker/EA/LTDs.md`

## Inputs reviewed

- `/docker/EA/LTDs.md`
- `.codex-design/product/LTD_CAPABILITY_MAP.md`
- `.codex-design/product/HORIZON_AND_FEATURE_LTD_INTEGRATION_GUIDE.md`
- `.codex-design/product/LTD_RUNTIME_AND_PROJECTION_REGISTRY.yaml`
- `docs/CHUMMER_RUN_FLAGSHIP_REDESIGN_PACKAGE.md`
- `docs/PUBLIC_LANDING_SURFACE.md`
- `.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
- `.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF_CHUMMER6_ALIAS.generated.json`
- `/home/tibor/chummer_reaudit_20260507_artifacts.zip`
- current code in `Chummer.Run.Api`, `Chummer.Run.AI`, `Chummer.Run.Identity`, `Chummer.Run.Contracts`, `scripts`, and tests

## Executive take

The main missed potential is not a lack of LTD ideas. The repo already carries more LTD intent than runtime reality. The highest-value move is to finish the seams that are already half-built and prove them with first-party receipts.

For the current follow-through direction, route proof is no longer the gating issue. The stronger next lever is customer-shape, shell cleanup, page editing, and a tighter set of LTD-backed product loops. See `CHUMMER_FLAGSHIP_CUSTOMER_SHAPE_GUIDE.generated.md`.

Current code-backed LTD lanes in this repo are concentrated in:

- `Emailit` for identity mail, support progress mail, and ProductLift-closeout delivery callbacks
- `ProductLift` as a first-party wrapped feedback, roadmap, changelog, operations, and closeout lane
- `BrowserAct`, `MarkupGo`, and `PeekShot` as hosted AI gateway adapters
- `1min.AI` and `AI Magicx` as routed provider identities in the gateway
- `Teable` as an internal user-projection workbench
- `ClickRank.ai` as a bounded public-site script injection on `chummer.run`
- `FacePop`, `Deftform`, `ICanpreneur`, `MetaSurvey`, and `Lunacal` as bounded first-party projections inside KARMA FORGE and public concierge flows

Everything else is mostly one of three things:

- canon and backlog intent
- bounded first-party projection without a direct vendor API adapter
- public-copy-safe placeholders for future bounded adapters

That distinction matters. Several LTDs are intentionally integrated through first-party packet truth and bounded workflow projection rather than direct third-party API calls.

## What is already materially real

### Code-backed now

- `Emailit`
  Evidence: `Chummer.Run.Identity/Services/IdentityEmailDeliveryService.cs`, `Chummer.Run.Api/Services/Support/SupportProgressEmailWorkflowService.cs`, `Chummer.Run.Api/Services/PublicSignalOperationsService.cs`
  Reality: this is one of the most mature LTD integrations in the repo.

- `ProductLift`
  Evidence: `Chummer.Run.Api/Controllers/PublicLandingController.cs`, `Chummer.Run.Api/Services/PublicSignalOperationsService.cs`, `Chummer.Run.Api/Views/PublicLanding/Feedback.cshtml`, `Roadmap.cshtml`, `Changelog.cshtml`
  Reality: the first-party wrapper is already substantial. This repo is not starting from zero here.

- `BrowserAct`, `MarkupGo`, `PeekShot`
  Evidence: `Chummer.Run.AI/Program.cs`, `Chummer.Run.AI/Services/Gateway/HttpProviderAdapters.cs`
  Reality: real adapter registration exists, but public proof workflows are still thinner than they should be.

- `1min.AI`, `AI Magicx`, `Prompting Systems`, `ChatPlayground AI`
  Evidence: `Chummer.Run.AI/Program.cs`, `Chummer.Run.AI/Services/Gateway/ProviderRouting.cs`
  Reality: these exist as routed provider identities, but only `1min.AI` and `AI Magicx` look like practical near-term lanes. `Prompting Systems` and `ChatPlayground` remain mostly scaffolding.

- `Teable`
  Evidence: `Chummer.Run.Api/Services/Community/TeableUserProjectionService.cs`, `TeableUserProjectionSyncWorker.cs`, `Controllers/InternalTeableUsersController.cs`
  Reality: this is a real internal projection seam, not just design prose.

- `ClickRank.ai`
  Evidence: `Chummer.Run.Api/Views/Shared/_Layout.cshtml`
  Reality: real host-gated script loading exists, but the improvement loop from findings to canonical source change is still manual.

### Proof state now

- Repo-local canonical route proof exists and currently passes: `63/63`
- Remaining opportunity: recurring phone viewport and tap-target evidence if the team wants stronger release discipline later, but that is not the current blocker

## Where the repo is overstating completion

These appear in code or tests as bounded first-party projections, not as fully externalized direct adapters:

- `FacePop`
- `Deftform`
- `ICanpreneur`
- `MetaSurvey`
- `Lunacal`

Evidence:

- `Chummer.Run.Api/Services/KarmaForge/KarmaForgeDiscoveryService.cs`
- `Chummer.Run.Api/Services/PublicConciergeService.cs`
- `Chummer.Run.Api/Services/PublicConciergeStore.cs`
- `Chummer.Run.Api/Services/Support/PublicSignalToCanonPacketService.cs`
- `Chummer.Run.Api/Services/PublicSignalOperationsService.cs`
- `Chummer.Run.Api/Views/PublicLanding/KarmaForge.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/KarmaForgeSubmitted.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Concierge.cshtml`
- `Chummer.Tests/KarmaForgeDiscoveryServiceTests.cs`
- `Chummer.Tests/PublicConciergeServiceTests.cs`
- `Chummer.Tests/PublicSignalToCanonPacketServiceTests.cs`

Examples:

- `FacePop`, `Deftform`, `ICanpreneur`, `MetaSurvey`, and `Lunacal` now project as bounded KARMA FORGE stages with explicit first-party status, labels, and receipt posture
- concierge branch routing persists first-party handoff receipts and moderation-safe fallback state before any external redirect occurs
- `productlift_signal`, `katteb_signal`, `clickrank_signal`, and `metasurvey_signal` now materialize as classified signal-to-canon packets instead of collapsing into one generic growth row

This is no longer just naming. The repo now carries a real bounded projection layer with tests. The remaining missed potential is deeper closure: more direct adapter depth, stronger cross-system receipts, and refreshed published proof.

## Highest-value missed potential

### 1. Turn BrowserAct + PeekShot + MarkupGo into a real public-proof factory

Why it matters:

- The route verifier is already green, but phone proof is still weak.
- The best next leverage is to produce redacted browser evidence, screenshots, and contact sheets for `/`, `/downloads`, `/now`, `/feedback`, `/roadmap`, `/changelog`, and `/help`.

What is missing:

- recurring phone screenshots
- first-screen CTA proof
- crop/contact-sheet output tied to real screenshots
- one bounded artifact packet that can be attached to release closeout

Best LTD combination:

- `BrowserAct` for route and auth-state capture
- `PeekShot` for screenshot/thumbnail generation
- `MarkupGo` for proof packet PDF/contact sheet

### 2. Finish the ProductLift loop instead of redesigning feedback again

Why it matters:

- This repo already has meaningful ProductLift wrapper work.
- The remaining gap is closer to ingestion, taxonomy, closeout, and operator proof than to UI invention.

What is missing:

- stronger domain split and explicit public wrapper posture
- better signal-to-design packet materialization
- stronger shipped-closeout proof back to voters
- less operator-facing `feedback/operations` exposure on the public surface story

Best LTD combination:

- `ProductLift`
- `Emailit`
- `Teable` for curated internal projections only
- `BrowserAct` for external board and closeout verification when needed

### 3. Promote the docs/search/AI-readable surface as a governed growth lane

Why it matters:

- `ClickRank.ai` is live in layout.
- `llms.txt` and `ai.txt` exist under `wwwroot`.
- The repo still underuses this seam as a first-class public discoverability loop.

What is missing:

- manifest-level proof for `llms.txt`
- a clearer source-backed refresh loop for public route summaries
- explicit ops rhythm for search findings to turn into source changes

Best LTD combination:

- `ClickRank.ai`
- `Documentation.AI`
- `Katteb` only downstream of approved source packets

### 4. Deepen the KARMA FORGE discovery ladder from bounded projection into fuller operational closure

Why it matters:

- The intended workflow is now present as a tested first-party projection.
- The next step is no longer basic existence. It is stronger external closure, follow-through receipts, and operator-grade proof.

What is missing:

- stronger end-to-end proof that every bounded stage closes back into first-party packet truth
- more explicit artifact receipts for external redirects and completed follow-up loops
- operator-facing review and closeout surfaces that consume the discovery packet directly

Best LTD combination:

- `Deftform` for pre-screen
- `ICanpreneur` for adaptive follow-up
- `MetaSurvey` for quant validation
- `Lunacal` for follow-up calls
- `ApproveThis` only if external sign-off becomes useful

### 5. Expand the artifact shelf with real media-factory proofs, not teaser copy

Why it matters:

- The product canon wants campaign primers, mission briefings, runsite visuals, narrated outputs, and replay-safe artifacts.
- The repo has the naming and some detail routes, but only part of the adapter reality.

What is missing:

- stronger first-party source packet to artifact receipts
- actual render-closeout packets
- clearer separation between concept art and proof artifacts

Best LTD combination:

- `VidBoard.ai`
- `Mootion`
- `First Book ai`
- `Soundmadeseen`
- `Nonverbia`
- `Unmixr AI`
- `MarkupGo`
- `PeekShot`

### 6. Make RUNSITE more than a named horizon

Why it matters:

- `RUNSITE` is one of the strongest LTD-to-product matches in the canon.
- The repo still underuses the spatial stack in a concrete public artifact way.

What is missing:

- repeatable runsite packet generation
- route/map visualization outputs
- stronger pre-session orientation artifacts

Best LTD combination:

- `Crezlo Tours`
- `AvoMap`
- `PeekShot`
- later `VidBoard.ai` or `Soundmadeseen` for orientation companions

## Full LTD-by-LTD assessment

### Finish or promote now

| LTD | EA detail that matters | Repo reality now | Best use in `chummer.run-services` | Call |
|---|---|---|---|---|
| `Emailit` | verified sender domain and active operational mail posture | real code-backed adapter and callback flow | identity mail, support progress, ProductLift closeout, install/support follow-through | finish and expand |
| `ProductLift.dev` | owned for feedback, voting, roadmap, changelog, signal capture | first-party wrapper is already substantial | finish ingestion, taxonomy, closeout, and proof loops | highest priority |
| `BrowserAct` | Tier 1 verification/capture lane | real gateway adapter | route verification, auth-path proof, feedback and install proof capture | finish with receipts |
| `PeekShot` | screenshot/thumbnail lane | real gateway adapter plus creative references | public proof thumbnails, phone screenshot contact sheets, artifact previews | finish with route proof pack |
| `MarkupGo` | document rendering lane | real gateway adapter plus creative use | route-proof packet PDFs, artifact contact sheets, audit receipts | finish with proof packet outputs |
| `1min.AI` | active credits, key rotation, fallback availability | routed provider identity exists | cheap internal synthesis for route summaries, packet drafts, and audit help | safe internal use now |
| `AI Magicx` | active fallback lane | routed provider identity exists | short overflow generation and bounded internal synthesis | safe internal use now |
| `Teable` | curated projection only, never truth | real internal projection service exists | admin workbench, feedback and ops projection boards | keep internal and bounded |
| `ClickRank.ai` | live public domain IDs already exist | real layout injection exists | crawl-health, metadata, AI-search and search visibility remediation loop | finish the ops loop |

### Strong opportunities, but still mostly design intent

| LTD | EA detail that matters | Repo reality now | Best use in `chummer.run-services` | Call |
|---|---|---|---|---|
| `Prompting Systems` | bounded prompt/style helper | mock provider identity and canon references | tone guardrails, artifact prompt normalization, public-copy refinement packets | next |
| `Documentation.AI` | intended for docs, cited answers, `llms.txt`, operator docs | public static `llms.txt` exists, but no real downstream automation lane here | AI-readable docs refresh, source-backed public help summaries, `llms.txt` stewardship | next |
| `Katteb` | intended for public content optimization | signal classification is now real, but downstream content-improvement closure is still thin | public guide/article optimization from approved source packets only | next after docs loop |
| `FacePop` | bounded trust/concierge widget only | bounded first-party concierge and discovery projection now exists with tests, but still not a direct adapter | public trust/concierge entry, never first-line support | active and bounded |
| `Deftform` | structured intake potential | bounded KARMA FORGE stage projection and public discovery rendering now exists | KARMA FORGE pre-screen and bounded discovery forms | active bounded pilot |
| `ICanpreneur` | discovery and validation lane | bounded KARMA FORGE adaptive interview stage now exists | adaptive follow-up interviews after signal clustering | active bounded pilot |
| `MetaSurvey` | structured follow-up survey lane | bounded KARMA FORGE and signal-classification lane now exists | quantitative follow-up after ProductLift or KARMA FORGE intake | active bounded pilot |
| `Lunacal` | scheduling follow-up lane | bounded KARMA FORGE follow-up scheduling stage now exists | public discovery follow-up or open-run scheduling after first-party receipts exist | active bounded pilot |
| `ApproveThis` | external approval observation lane | canon-backed, no direct adapter in this repo | external sign-off observation for governed publication or review queues | later pilot |
| `VidBoard.ai` | presenter-video lane | mostly canon-backed here | campaign primer or mission-brief preview videos on artifact shelf | media-factory next wave |
| `Mootion` | scaffold-stage motion/video lane | canon-backed here | preview-only motion artifacts | media-factory next wave |
| `First Book ai` | long-form authoring lane | canon-backed here | player primers, campaign packets, runbook press drafts | media-factory next wave |
| `Soundmadeseen` | narrated media lane after verification | canon-backed here | narration, recap, and newsreel-style artifact support | later media lane |
| `Nonverbia` | coaching/social analysis lane | canon-backed here | bounded debrief or coaching artifacts, not runtime truth | later horizon lane |
| `Unmixr AI` | candidate voice lane | canon-backed here | optional voiced variants for approved scripts only | later media lane |
| `AvoMap` | route/location visualization | canon-backed here | runsite maps and pre-session orientation visuals | strong later fit |
| `Crezlo Tours` | explorable tour pipeline exists elsewhere in EA | not materially integrated here | runsite location tours and pre-brief walk-throughs | strong later fit |
| `hedy.ai` | meeting capture and commitment extraction | no real adapter here | operator interviews, community follow-up evidence, debrief prep | useful, but not urgent |
| `Signitic` | passive campaign amplification lane | canon-backed, not integrated here | passive recruitment, release, and world-tick projection into first-party destinations | low urgency |
| `GetNextStep.io` | process execution/checklist lane | mostly canon language, not adapter reality | governed process execution for ops runbooks and closeout checklists | low urgency unless ops discipline needs it |

### Tracked or parked

| LTD | EA detail that matters | Repo reality now | Best use in `chummer.run-services` | Call |
|---|---|---|---|---|
| `ChatPlayground AI` | tracked eval workspace only | mock provider identity only | provider-comparison lab, not product runtime | park |
| `Paperguide` | cited research helper | canon only | internal design research, citation support | park |
| `Vizologi` | strategy research only | canon only | strategy and horizon ideation | park |
| `ApiX-Drive` | low-risk automation glue only | canon only | glue only if a specific low-risk ops task appears | park |
| `FineTuning.ai` | bounded media-only future lane | almost no repo reality | sonic cue and media bed support after artifact receipts are mature | park |
| `Internxt Cloud Storage` | archive/retention utility | not product-shaped here | cold archive only | park |
| `FastestVPN PRO` | ops privacy utility | irrelevant to product surface | ops only | non-product |
| `OneAir` | travel utility | irrelevant here | none | non-product |
| `Headway` | knowledge utility | irrelevant here | none | non-product |
| `Invoiless` | billing utility | irrelevant here | none | non-product |

### Need explicit no-hype treatment

| LTD | Why it is easy to misuse | Safe posture |
|---|---|---|
| `FacePop` | can become a fake support solution too early | keep out of first-line support until support receipts are strong |
| `Katteb` | can invent public claims | use only from approved source packets |
| `Documentation.AI` | can drift into invented docs | source-backed summaries only |
| `VidBoard.ai`, `Mootion`, `Soundmadeseen`, `Unmixr AI` | can make preview media look more real than product truth | previews only, always downstream of source packets |
| `Teable` | can quietly become shadow truth | projection only, never system of record |

## Concrete gaps that should be closed next

1. Add recurring phone/public screenshot proof for the public route family using `BrowserAct` plus `PeekShot`.
2. Add a `MarkupGo`-backed route-proof packet or contact sheet so public release proof is easier to review and archive.
3. Finish the ProductLift closeout loop so public signal, shipped status, and follow-up receipts visibly connect.
4. Promote the docs/search lane with explicit `llms.txt` stewardship, route-summary refresh, and ClickRank-fed remediation cadence.
5. Keep closure proof current so the bounded KARMA FORGE, concierge, and growth-classification integrations stay reflected in published readiness truth.
6. Turn RUNSITE into a real artifact lane using `Crezlo Tours`, `AvoMap`, and `PeekShot`.
7. Build one real media-factory receipt path for campaign primer or mission brief artifacts before expanding the rest of the video/audio stack.

## Important canon drift observed during this audit

- `PUBLIC_AUTH_FLOW.md` currently disagrees with the manifest and controller behavior for guest fallback on `/participate/codex`.
- `docs/PUBLIC_LANDING_SURFACE.md` and `PUBLIC_LANDING_MANIFEST.yaml` agree with the actual controller on the Google-start fallback.
- That means the public auth canon is drifting in-repo even though the public-surface canon and implementation are aligned.

This is not a flagship redesign issue. It is a truth-discipline issue.

## Bottom line

The repo already has enough LTD surface to ship a stronger product loop without buying or inventing anything new.

The best leverage is:

- finish the already-real proof and closeout seams
- deepen the already-bounded discovery ladders into stronger end-to-end receipts and operator closure
- resist calling queue labels “integrations”
- keep public truth first-party even when the LTD stack gets richer
