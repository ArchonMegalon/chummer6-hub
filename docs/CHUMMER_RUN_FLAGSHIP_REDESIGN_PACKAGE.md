# Chummer.run Flagship Redesign Package

Date: 2026-05-06
Scope: `chummer.run` public route family, account-aware front door, ProductLift fallback posture, and the first implementation slice in `chummer.run-services`
Status: the major route-family redesign slices are already landed in this repo; use this package as the shipped baseline and follow-through guide, not as a greenfield restart brief.

## 1. Audit Summary

Live observation on 2026-05-06, amended by the 2026-06 minimalist front-door pass:

- `/`, `/downloads`, `/now`, and `/roadmap` carry the normal public route family. `/horizons` is now a noindex maintenance alias for older links, not a product shelf.
- `/participate` and `/help` still read like a different, flatter product shell. The route family loses visual continuity precisely where the user needs trust and guidance.
- The current front door strongly communicates "explainable rules truth" but under-projects "campaign command surface", "who this is for", and "why the account-aware return path matters".
- Install, support, and device-linking truth exists, but it is presented as compliance plumbing rather than as a premium continuity benefit.
- ProductLift honesty is good: first-party fallback routes remain visible and source truth stays inside Chummer-owned surfaces.

What is already working:

- One concrete proof result is visible on the landing page.
- Downloads posture is honest about recommended install, known issues, and platform gaps.
- `/now` does real decision support instead of marketing theater.
- `/roadmap` shows public direction without pretending planned work is shipped.
- Account-aware handoff, claim-linking, and support continuity already have real canonical seams.

What is still weak:

- The landing page must keep converting the visible result into a fuller product story.
- The route family does not yet feel like one flagship product system.
- GM, player, and creator fit are present in canon, but underused on the front door.
- The visual hierarchy must stay "install and product clarity first, deeper checks second".

## 1A. Current Shipped Baseline (2026-05-07)

This package started as the 2026-05-06 audit, and several of the weaker spots listed above have already been tightened. Do not restart this work from a blank redesign prompt. The repo already ships most of the route-family work described below:

- `Chummer.Run.Api/Views/PublicLanding/Landing.cshtml` already projects canon `start_here`, `why_trust_it`, `choose_your_lane`, continuity, and flagship-coverage sections onto the live landing route.
- `Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml`, `Now.cshtml`, `Participate.cshtml`, `Roadmap.cshtml`, `Shelf.cshtml`, `ProductStory.cshtml`, and `TrustPage.cshtml` already share the stronger flagship shell language, route-choice cards, check rails, and first-party truth boundaries.
- `Chummer.Run.Api/Views/PublicLanding/Home.cshtml`, `Chummer.Run.Api/Views/Accounts/Account.cshtml`, `Chummer.Run.Api/Views/Auth/Entry.cshtml`, and `Chummer.Run.Api/Views/Shared/_Layout.cshtml` already carry the signed-in continuation, auth-value, shared navigation, and mobile CTA work.
- `Chummer.Tests/PublicLandingReleaseTrustViewTests.cs` and related route/view tests already fail closed on the core route-family expectations, so new work should extend those guardrails instead of bypassing them.

Use that shipped baseline. The remaining work is not "redesign chummer.run again". It is incremental flagship compression: keep route-family coherence tight, improve thinner sibling routes without breaking canon truth, and prefer extending the current component families over inventing a second visual system.

## 2. Non-Negotiable Product Truth

- Keep the public product name as `Chummer`. Do not rename the live front door to "RunDeck" or another alternate brand.
- Keep the core public promise as explainable Shadowrun plus durable continuity, not generic productivity.
- Preserve one public front door: guest-readable install and learning, signed-in better handoff, no parallel auth or participation story.
- Preserve first-party truth boundaries: `what works today`, `status`, downloads evidence, and help/support routes remain the authority surfaces.
- Preserve ProductLift as projection, not canon. Public signal may inform direction; it does not become the roadmap source of truth.
- Preserve Tibor's Mac build trigger path and release-upload workflow exactly.

## 3. Strategic Direction

Recommended positioning:

> Chummer is the explainable Shadowrun campaign companion.

Not because the site should become a fake enterprise dashboard, but because the current product truth already supports three premium promises:

1. Rules results you can inspect.
2. Campaign continuity that survives device drift.
3. Account-aware follow-through for installs, support, roadmap interest, and return-to-work.

The redesign should make those three promises legible on every major route.

## 4. Experience Model

The flagship public surface should feel like:

- a serious campaign operating deck
- a premium dossier and continuity system
- a product that knows the difference between current downloads, deeper checks, and future work

It should not feel like:

- an internal control plane with cyberpunk wallpaper
- a generic SaaS dashboard
- a roadmap-voting microsite with a game theme
- a browser ritual that hides the real install and recovery path

## 5. Visual Direction

Direction:

- Light-to-deep blueglass palette, not neon overload.
- Big editorial display type paired with technical mono proof notes.
- Premium dossier surfaces, record rails, and route callouts.
- Atmospheric stills that imply campaign pressure, dossiers, devices, desks, transit, rain, and continuity.
- Motion only where it helps sequencing: staged reveal, proof-float rise, route-callout slide, and trust-rail fade.

Typography:

- Keep `Space Grotesk` or another display face for editorial headlines.
- Keep `Instrument Sans` for reading copy.
- Keep `IBM Plex Mono` for receipts, route IDs, proof trails, and support/status microcopy.

Color system:

- Primary glass: deep navy and desaturated cobalt.
- Proof accent: colder cyan-blue, not bright purple.
- Decision accent: warm brass or parchment-tan for "recommended" and "current build" cues.
- Caution accent: ember-orange only where caution is real.

Component families:

- Hero result float
- Route callout
- Workflow cards
- Trust cards
- Role or route choice cards
- Release shelf cards
- Support decision cards
- Milestone drawer cards

## 6. Route Family Strategy

| Route | Primary job | Stop doing | Inherit | Visual density | Mobile simplification | CTA posture | Validation posture |
|---|---|---|---|---|---|---|---|
| `/` | Explain who Chummer is for | Acting like only a checks page | Hero result float, workflow band, trust band, role-fit grid | High | Collapse into stacked hero, trust, lanes | Primary install/account CTA, secondary `what works today` | One concrete result, trust pulse, role fit |
| `/what-is-chummer` | Tell the product story | Repeating downloads or roadmap verbatim | Editorial hero, trust pillars, route family links | Medium | Story blocks only | Primary `downloads`, secondary `status` | Validation examples inline, no release shelf duplication |
| `/downloads` | Get the user onto the right build safely | Letting extra files crowd the install decision | Shared header, trust rail, help adjacency | Medium | Recommended platform first, details collapsed | Stable and Nightly first, account optional | Build date, platform state, known issues |
| `/now` | Help users decide install now vs wait | Reading like changelog fluff | Workflow cards, release posture, signed-in return rail | Medium-high | Keep 3 core validation cards, collapse supporting validation | Primary `downloads`, secondary `status` | Live, preview, and caution all explicit |
| `/horizons` | Compatibility maintenance alias for older links | Being promoted like a product section | Minimal pointer back to Downloads, Help, Status, and Roadmap | Low | One short maintenance page | Primary `downloads`, secondary `roadmap` | Noindex, not promoted |
| `/roadmap` | Show milestone-backed direction | Redirecting back to a softer summary shelf | Milestone drawer, planned-work cards, public loop framing | High | Keep cards collapsed by default | Primary detail routes, secondary `status` | Milestone difficulty, claimed state, dependencies |
| `/artifacts` | Make supporting files tangible | Becoming a junk drawer | Publication gallery, publication rail, route-boundary copy | Medium | Featured file stack | Primary file details, secondary `downloads` | Evidence-first, not hype-first |
| `/participate` | Route signal safely to public or signed-in lanes | Mixing support, contribution, and roadmap authority | Trust claims, route choice cards, public loop stages | Medium | Two primary paths: public and signed-in | Primary public route, secondary signed-in route | ProductLift boundary, first-party fallback honesty |
| `/help` | Triage install, account, and product help fast | Acting like a legal FAQ | Support decision cards, downloads and contact adjacency | Medium | Three biggest jobs first | Primary support intake, secondary `downloads` | First-party support truth only |
| `/faq` | Answer normal product questions plainly | Becoming a catch-all support form | Plain-language cards, route links | Low-medium | Accordion or stacked Q/A | CTAs back to help/downloads | Validation via route references, not screenshots |
| `/privacy` | Bound trust around data handling | Sounding like generic SaaS boilerplate | Calm legal shell, route adjacency | Low | Short sections | No sales CTA; help context only | Explicit scope and retention boundaries |
| `/terms` | Bound preview usage expectations | Carrying marketing language | Calm legal shell | Low | Short sections | No sales CTA; help context only | Preview and support boundary only |
| `/contact` | Start first-party help with the right expectation | Competing with ProductLift | Same support decision language as `/help` | Medium | Single intake path and escalation notes | Primary support intake | Private follow-up boundary explicit |
| `/signup` | Convert interest into a stable return path | Overselling community or auth providers | Shared flagship shell, boring auth copy | Low-medium | One form, one reason, one fallback | Primary create account | Recovery and install follow-through cues |
| `/login` | Restore access cleanly | Acting like a social-auth showcase | Same auth shell as signup | Low-medium | One form, one recovery link | Primary sign in | Recovery path and next route explicit |
| `/home` | Show what changed for me | Becoming a generic dashboard | Home cockpit, campaign rail, install role cues | High | Continue card first | Primary continue | Campaign, install, and support state together |
| `/account` | Manage access, devices, linked state, support history | Repeating marketing | Account modules, devices/access truth, linked identity rails | Medium | Compact settings clusters | Primary next safe account action | Device role, install, identity, and support truth |

## 7. Copy Skeleton

- Global nav: `Product`, `Downloads`, `What works today`, `Roadmap`, `Artifacts`, `Participate`
- Hero eyebrow: `Explainable Shadowrun`
- Hero headline: `Build a runner, explain every ruling, and recover the campaign.`
- Hero subheadline: `Start with the current build, inspect the modifier trail, and keep the next session moving with explainable math, durable state, and visible recovery paths.`
- Hero CTA pair: `Open downloads` / `See what works today`
- Result section headline: `One concrete result, one visible trail, one current build`
- What's-live-now strip: `What works today, what needs care, what is next`
- Downloads summary: `Start with the one recommended build for this device, then use status and help without leaving the same truth rail.`
- Roadmap intro: `Direction stays visible, but readiness and dependencies stay attached.`
- Files intro: `Packets and publication outputs that make the product tangible without inflating maturity claims.`
- Final CTA band: `Create the account that keeps your place`
- Account-value microcopy: `Installs, devices, roadmap follow-up, and support history stay attached to one return path.`
- Support/help microcopy: `Use first-party help for installs, account recovery, and practical product trouble before you fall through to public issue lanes.`
- Install-linking microcopy: `The signed-in handoff gives you a better return path, not a different public build.`
- ProductLift microcopy: `Fixer Board stays public and useful, but source truth still lives inside Chummer-owned routes.`

Tone rules:

- sharp
- premium
- modern
- direct
- serious
- not melodramatic
- not corporate

## 8. Art Direction and Prompt Set

Global prompt rules:

- professional
- premium
- cyberpunk but controlled
- Shadowrun-adjacent campaign OS atmosphere
- no readable text
- no logos
- no poster cliches
- no generic filler
- no fake vector or SVG look
- no meaningless signage

Prompts:

1. Flagship hero: `Rain-heavy blueglass operations desk inside a Shadowrun-safe campaign workspace, dossier stacks, soft holographic route traces, grounded hardware, one premium result screen, cinematic but restrained, no text, no logos`
2. Result section: `Close-up of a rules result panel with dice math notes, source tabs, check markers, and one trusted result, cool cobalt lighting, tactile materials, no text, no logos`
3. Downloads/install confidence: `Premium install handoff scene with sealed package, device silhouette, claim record, support notes, calm trust posture, deep navy and steel palette, no text`
4. Roadmap/futures: `Blue boulevard reflections and distant wayfinding markers suggesting future product lanes, evidence tags and measured wayfinding, restrained cyberpunk, no text`
5. Files/dossier shelf: `Curated evidence shelf with briefing cards, publication packets, camera stills, and physical dossier objects, museum-grade lighting, no text`
6. Participation/signal lane: `Public signal board with clean route splits between feedback, roadmap, and support, human-scale control surfaces, premium interface realism, no text`
7. Help/support: `Quiet support desk with device, recovery notes, contact rail, and trustworthy first-party service atmosphere, premium but not sterile, no text`
8. Mobile continuity: `Compact mobile campaign continuity scene with one dossier carried across phone, tablet, and laptop under rain-lit transit light, no text`
9. Campaign continuity: `Runboard memory scene with aftermath cues, contact notes, heat traces, and next-session prep in one grounded workspace, no text`
10. Player / GM / creator fit: `Triptych of player-safe brief, GM operations board, and creator publication desk, cohesive lighting family, premium editorial composition, no text`
11. Signed-in access/device continuity: `Claimed install and account-linked devices represented as coordinated hardware on one trust rail, clean receipts, quiet blue light, no text`
12. Alternate hero family: `Black-glass safehouse workspace with premium practical lighting, dossier fragments, world map overlays, and one active campaign artifact, no text`

## 9. Auth, Install, and Device-Linking Preservation Plan

Must remain true:

- One public front door; public learning and install, signed-in better handoff.
- Guest-readable downloads stay guest-readable where canon permits.
- Signed-in users may receive `DownloadReceipt` and `InstallClaimTicket` handoff, not a personalized binary.
- `/participate` remains the guest-readable account-aware participation entry.
- `/home` and `/account` remain the signed-in continuation and device/access shells.
- Identity, install, and linked channels remain separate records.

Preservation rules:

- Do not move provider-specific language into hero or public product-story copy.
- Do not replace the boring account-recovery path with a browser-only claim-code ritual.
- Keep `Devices and access` discoverable from the signed-in shell, not buried in support copy.
- Keep mobile return safety centered on the same account-aware handoff: install receipt, claimed device, support history, and roadmap follow-up all return to the same account surface.
- Signed-in CTAs should always deepen the return path, not gate public truth.

## 10. Tibor Mac Build Compatibility Plan

Current path to preserve:

- The hosted signed-in entry is `/downloads/release-upload`.
- The public bootstrap endpoint is `/downloads/release-upload/bootstrap.sh`.
- The local bootstrap source file is `Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh`.
- The repo wrapper is `scripts/run-mac-release-bootstrap.sh`.
- Live parity verification is `scripts/verify-live-mac-bootstrap.sh`.

Do not break:

- Generated command blocks from the signed-in release-upload page.
- Short-lived upload ticket and API-token support.
- Hosted SHA-checked bootstrap flow.
- Legacy bootstrap redirect behavior.
- `Cache-Control: private, no-store, max-age=0` posture on the legacy route.

Safe improvements:

- Better public explanation around the Mac path on `downloads` and artifact detail surfaces.
- Stronger visual presentation of the release-upload runbook.
- Better release-proof adjacency on the Mac artifact shelf.

Required evidence:

- `scripts/verify-live-mac-bootstrap.sh`
- local and hosted bootstrap SHA parity
- `HUB_LOCAL_RELEASE_PROOF.generated.json`
- existing Mac bootstrap and install-linking tests

## 11. LTD Utilization Map

- `1min.AI` — Tier 1, live now. Role: signal-core generation for explainers, recaps, and compact campaign briefs inside signed-in and artifact routes. Target: `home` cockpit briefs, campaign memory packet summaries, artifact annotations. Dependencies: prompt envelopes and campaign truth inputs. Verify: generated receipt plus workflow test coverage. Touches: signed-in workspace routes and publication workflows.
- `BrowserAct` — Tier 1, live now. Role: Matrix Scout and external evidence capture. Target: external fact capture, public-signal enrichment, proof packet generation, and guide-source extraction. Dependencies: connector bindings and evidence packet routes. Verify: BrowserAct receipt trails and artifact generation. Touches: artifact workflows, support or signal triage, future scout surfaces.
- `Emailit` — Tier 1, live now. Role: dispatch and follow-through lane. Target: recap mails, support closeout notices, preview follow-up, and shipped notification mail. Dependencies: sender-domain health and account-aware notification rules. Verify: delivery receipts and route-triggered tests. Touches: support loops, roadmap follow-up, signed-in account value.
- `AI Magicx` — Tier 1, live now. Role: bounded fallback lane for short overflow generation. Target: helper copy, overflow recap generation, and support-safe summarization. Dependencies: prompt limits and 1min.AI fallback rules. Verify: fallback path tests. Touches: summary generation, not hero marketing.
- `Prompt Architects` — Tier 2, staged next. Role: voice tuner for premium copy and media prompt consistency. Target: editorial copy pass templates, image prompt normalization, and route-family tone guardrails. Dependencies: prompt-packet wiring. Verify: prompt packet receipts and review diffs. Touches: design-system copy and creative ops.
- `ApproveThis` — Tier 2, staged next. Role: Johnson sign-off lane for creator publication or governed future approvals. Target: bounded approval queue views on creator and publication flows. Dependencies: BrowserAct queue reading and approval taxonomy. Verify: approval packet artifact. Touches: creator/publication follow-through, not core landing.
- `MetaSurvey` — Tier 2, staged next. Role: crew pulse and post-preview feedback collection. Target: signed-in beta and support sentiment loops, not public front-door gating. Dependencies: account-aware follow-up and taxonomy mapping. Verify: survey extraction packets. Touches: signed-in follow-up surfaces.
- `ProductLift.dev` — Tier 4, future projection seam. Role: Fixer Board once promoted. Target: public feedback intake, voting, roadmap projection, changelog closeout, and webhook-fed signal clustering. Dependencies: domain split, API or webhook ingestion, design-triage mapping. Verify: hosted adapter receipt, public route parity tests, queue packet evidence. Touches: `/feedback`, `/roadmap`, `/changelog`, signal ingestion loops.
- `Documentation.AI` — Tier 4, future docs seam. Role: lorebook and public guide production support. Target: support and guide freshness for help, FAQ, and later docs surfaces. Dependencies: site allocation, sync wiring, freshness verification. Verify: doc freshness receipts. Touches: help, FAQ, operator docs.
- `Mootion` — Tier 2, staged next. Role: controlled motion or scene forge extension for video-like packets. Target: artifact shelf motion packets and creator publication media. Dependencies: render scaffold promotion. Verify: media render receipt. Touches: artifacts and creator publication only.
- `AvoMap` — Tier 2, staged next. Role: map or route visualization extension for campaigns and run prep. Target: future campaign workspace map packets and artifact visuals. Dependencies: staged local integration. Verify: render or packet receipt. Touches: later runboard and artifact flows.
- `FineTuning.ai` — Tier 4, future seam. Role: audio wardrobe and bounded sonic cue support. Target: recap or publication companion media, not first-wave product proof. Dependencies: provider adapter and first smoke run. Verify: media-factory receipt. Touches: future creator/publication surfaces.
- `ICanpreneur` — Tier 4, future seam. Role: internal "Venture Johnson" triage support for which public requests deserve investment. Target: operator decision packets downstream of ProductLift and support clusters. Dependencies: signal ingestion and bounded internal workflow. Verify: decision packet evidence. Touches: internal design triage, not public promise.

## 12. ProductLift Implementation Package

Public entry points:

- `/feedback` remains the public idea and safe public bug alias.
- `/roadmap` remains the public milestone-backed direction route.
- `/changelog` remains the shipped-closeout alias.

Behavior:

- Until ProductLift is promoted, each alias stays first-party and honest.
- Once promoted, ProductLift becomes the public signal and projection layer, not the roadmap source of truth.
- Public signal categories must map back to Chummer-owned taxonomy and route to help instead of ProductLift when the issue needs logs, recovery, or private campaign state.

Account-aware behavior:

- anonymous users may read and vote only if public moderation rules permit it
- signed-in users may subscribe to follow-up and beta interest through Hub-owned account state
- no ProductLift record becomes account truth, entitlement truth, or support-case truth

Ingress:

- webhook or API ingestion into a hosted adapter
- normalize to Chummer signal taxonomy
- cluster into design or support packets
- close the loop back to ProductLift changelog only after route, release, or support proof exists

Canonical-boundary rules:

- ProductLift statuses are public approximations
- internal roadmap truth remains in design canon and release-backed route state
- support, installs, accounts, and private cases stay first-party

Rollout order:

1. keep first-party fallback routes
2. add hosted adapter and ingestion
3. expose mirrored public board or redirect
4. wire roadmap and changelog projections
5. add account-aware follow and notification behavior

Build now:

- maintain first-party Fixer Board, roadmap, and changelog fallback routes
- keep route callouts and truth boundary copy

Build next:

- adapter, webhook ingestion, queue synthesis, and public signal taxonomy enforcement

## 13. Developer Handoff

Priority order:

1. strengthen the landing page into a fuller flagship front door
2. unify `/participate` and `/help` with the flagship route-family shell
3. sharpen `/downloads` and `/now` visual cadence without weakening trust posture
4. improve `/roadmap` detail density and `/artifacts` gallery polish
5. only then promote ProductLift-hosted projection

Current follow-through priority on 2026-05-07:

1. Treat the route-family redesign above as materially shipped across the main public routes; do not reopen it as a blank audit.
2. Tighten thinner sibling routes such as `/status`, minor trust/legal rails, and signed-in detail density only when they visibly lag the stronger landing/downloads/help/participate/roadmap/artifact shell.
3. Keep canon projection and fail-closed view tests current whenever route-family components, copy boundaries, or install/support truth move.
4. Revisit larger visual structure only if a concrete route has drifted away from the shipped component family or the mirrored canon changed.

Reusable components:

- hero result float
- workflow band and workflow cards
- trust claims grid
- route choice cards
- route callout
- release shelf cards
- signed-in return rail

Responsive breakpoints:

- desktop: wide hero and dual-rail sections
- tablet: stacked hero media, two-column card grids
- mobile: single-column cards, CTA pairs stacked, proof microcopy condensed

Image specs:

- wide hero still: 16:10 and 21:9 safe crops
- workflow cards: 4:3 or 3:2
- artifacts and route cards: 4:3
- no text embedded in images

Design QA checklist:

- route family feels like one product
- landing clearly shows product fit, trust, and return path
- downloads still prioritizes recommended install over art or roadmap
- help and participate never blur support and ProductLift roles
- research routes never read as shipped

Accessibility checklist:

- preserve text contrast against all atmospheric media
- all hero proof data remains text, not image-only
- CTA order remains logical in keyboard navigation
- trust and caution language stays readable without color alone

Performance checklist:

- use existing asset slots before adding new media families
- preserve responsive image handling
- avoid JS-driven hero gimmicks
- keep route-family enhancements CSS-first where possible

First implementation slice:

- Project the existing `start_here`, `why_trust_it`, and `choose_your_lane` canon onto `/`.
- Reuse existing `workflow-card`, `trust-claim`, and `route-choice-card` patterns.
- Keep all install, trust, and support CTAs on their current routes.
- Add tests that fail closed if those canon sections disappear from the landing view again.
