# Chummer.run Flagship Customer-Shape Guide

Date: 2026-05-07  
Scope: public Hub surfaces, signed-in shell, and LTD-backed improvement lanes

## Position

The Hub is now coherent. It is not yet flagship.

The remaining problem is not missing routes. The remaining problem is product editing:

- shell clutter
- repeated trust and status furniture
- too much internal vocabulary
- too many pages trying to do multiple jobs
- signed-in surfaces that still feel dense instead of calm

This guide assumes route proof is good enough for now. The next gains are visual, structural, and customer-shape gains.

## Keep these

- The account-aware install path on Downloads
- The first-party Help and Contact flow
- Signup explaining what the account actually gives
- The support form as a guest-capable, attachment-capable, expectation-setting first-party intake

These are already among the strongest parts of the current Hub.

## Blunt verdict

The current site still reads too much like an internal control plane that has been made public, rather than a premium product front door.

The strongest recurring issues are visible directly in the views:

- `Chummer.Run.Api/Views/Shared/_Layout.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Landing.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Now.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Horizons.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/FeatureDetail.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Participate.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/TrustPage.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Home.cshtml`
- `Chummer.Run.Api/Views/Accounts/Account.cshtml`

The signed-in density problem is still obvious in file size alone:

- `Home.cshtml`: `1543` lines
- `Account.cshtml`: `5069` lines

## Immediate design findings

### 1. The shared shell is still overbuilt

`_Layout.cshtml` still behaves like an expanded sitemap instead of a calm wrapper.

Concrete evidence:

- mobile sheet headings include `Navigate`, `Actions`, `Public loop`, and `Help and legal`
- footer repeats `Public loop` and `Help and legal`
- footer still carries provenance and internal-truth framing on public pages

This makes Product, Roadmap, Artifacts, and Contact feel cluttered before the page-specific content even begins.

### 2. The trust and status furniture is still over-distributed

The same public trust/status framing appears across too many surfaces. Even when the wording changes, the user experience remains the same:

- route-callout
- trust-rail
- compact proof bands
- repeated “use this rail for X, not Y” framing

That pattern is acceptable on `/progress` and selectively on `/now`. It is too heavy on flagship-facing product pages.

### 3. Public copy is still too internal

The public surfaces still overuse words like:

- `rail`
- `shelf`
- `proof`
- `artifact`
- `route`
- `Fixer Board`

Those are useful design or ops concepts. They are not premium public language at this saturation level.

### 4. Landing is coherent but not edited

The landing page currently carries too many stories at once:

- hero
- install handoff
- proof panel
- works-now shelf
- whole-product frontier
- workflow cards
- trust
- audience
- account value
- future material

That is not a missing-content problem. It is an editing problem.

### 5. Downloads is still too much of a super-template

The decisive install path exists, but the page still sprawls into product exposition, platform explanation, verification rail material, and artifact-style detail.

It needs to feel like one decisive install surface with advanced material hidden below the fold.

### 6. `/now` still mixes readiness, proof, and release explanation

The proof cards are useful. The page around them is still trying to do too many jobs.

The correct split is:

- Ready to install?
- What you can verify now.

### 7. Roadmap and Artifacts still read like long editorial shelves

`Horizons.cshtml` and `Shelf.cshtml` still spend too much space on route-family explanation and not enough on clean browsing.

In particular:

- `Horizons.cshtml` still uses `Fixer Board`, “future shelf”, and route-family explanation heavily
- `Shelf.cshtml` still mixes customer proof with operator or release-infrastructure proof language

### 8. Detail pages are still too template-obvious

`FeatureDetail.cshtml` has better action shaping than before, but the page family still feels too uniform across:

- live proof
- preview concept
- roadmap detail

Those families need visibly different structures, not only different copy.

### 9. Participate, Help, FAQ, Privacy, and Terms still inherit too much product-control tone

The substance is better than before.
The page posture is still too internal.

Best target states:

- Participate: feedback, beta, contribution only
- Help: triage hub
- FAQ: searchable or accordion answer surface
- Privacy and Terms: quiet policy pages

### 10. Signed-in surfaces still need a harder split

The views remain too big and too multi-job to feel premium.

Target split:

- Home: `Overview`, `Work`, `Access`, `Setup`
- Account: `Profile`, `Sign-in`, `Recovery`, `Devices & access`, `Support`

Advanced details should be hidden by default.

## Priority order

### P1

1. Rebuild the shared shell in `_Layout.cshtml`
2. Remove trust-pulse sprawl from flagship-facing pages
3. Rewrite public copy away from internal route/rail/shelf language
4. Edit Landing down to one story

### P2

1. Make Downloads brutally task-specific
2. Split `/now` into readiness and proof
3. Rebuild Roadmap and Artifacts as real browsers
4. Give detail-page families distinct layouts

### P3

1. Simplify Participate, Help, FAQ, Privacy, and Terms
2. Finish the signed-in split across Home and Account
3. Single-source status, install, and support taxonomy

## LTDs that should improve the Hub directly

These are the best direct Hub-improvement lanes.

### Use now

- `1min.AI`
  Use for rapid premium still generation and creative variants for flagship presentation work.

- `Emailit`
  Use for signup, install, support, beta, and closeout transactional mail.

- `BrowserAct`
  Use for visual QA, screenshot harvesting, and broken-flow detection.

- `ClickRank.ai`
  Use for SEO and AI-search audits on `chummer.run`.

- `Documentation.AI`
  Use for Help, FAQ, docs, and AI-readable route-summary freshness.

- `ProductLift.dev`
  Use for feedback, prioritization, roadmap/changelog projection, and signal loops.

- `MetaSurvey`
  Use for lightweight structured follow-up after feedback or download/help events.

- `PeekShot`
  Use for automated screenshots and proof thumbnails.

- `MarkupGo`
  Use for image/PDF artifacts, release one-pagers, and polished support or roadmap packets.

- `Lunacal`
  Use for demos, creator calls, or interview scheduling when higher-trust booking matters.

- `Signitic`
  Use for consistent support/demo outbound signatures.

## LTDs to use selectively

- `Soundmadeseen`
- `VidBoard.ai`
- `FacePop`
- `FineTuning.ai`
- `Mootion`
- `Unmixr AI`
- `ApiX-Drive`
- `ApproveThis`
- `Deftform`
- `katteb.com`
- `Teable`
- `AvoMap`
- `Crezlo Tours`

These are supporting tools, not the core flagship surface.

Rules:

- media tools support explainers, walkthroughs, proof assets, and social proof media
- `Teable` stays curated projection only
- `Deftform` stays fallback form infrastructure only if native Hub forms lag
- `FacePop` does not belong on the flagship hero or first-line support flow
- `Katteb` is downstream SEO drafting only, never public truth

## LTDs to keep internal

- `Prompting Systems`
- `ChatPlayground AI`
- `AI Magicx`
- `hedy.ai`
- `Nonverbia`
- `Paperguide`
- `Vizologi`
- `ICanpreneur`
- `First Book ai`
- `GetNextStep.io`

These can improve team throughput, research, strategy, copy prep, or internal process quality without appearing as public Hub features.

## LTDs that should not steer this redesign

- `FastestVPN PRO`
- `OneAir`
- `Headway`
- `Internxt Cloud Storage`
- `Invoiless`

These are not meaningful flagship Hub redesign levers.

## Actual LTD execution order

### 1. ProductLift.dev + MetaSurvey

Use them to build the real feedback loop first.

Target:

- `/feedback` stays first-party
- public votes and follow loops become useful
- roadmap and changelog projection become cleaner
- follow-up surveys catch what downloads, help, and feedback are missing

### 2. BrowserAct + PeekShot

Use them for visual QA, screenshot capture, and flow checks across:

- Landing
- Downloads
- Now
- Horizons
- Artifacts
- Help
- Signup
- Login
- Contact

### 3. Documentation.AI

Start small on Help and FAQ.
Do not let it widen into uncontrolled docs generation.

### 4. ClickRank.ai, then Katteb cautiously

Run the real SEO and AI-search pass first.
Only use `Katteb` later for source-backed drafts and expansions.

### 5. Emailit + Signitic + Lunacal

Tighten support receipts, download confirmations, beta invites, demos, and creator conversations.

### 6. 1min.AI + the media stack

Use media tooling for:

- proof clips
- narrated demos
- subtitled walkthroughs
- clean release explainers

Do not let it turn into autoplay clutter or mood fluff.

## What to implement first in code

1. `_Layout.cshtml`
   Remove sitemap behavior, compress footer, and stop repeating public-loop/help-legal structures.

2. `Landing.cshtml`
   Cut the page to one flagship story and move overflow story material elsewhere.

3. `Downloads.cshtml`
   Collapse advanced material and make the install decision path obvious.

4. `Now.cshtml`
   split readiness from proof.

5. `Horizons.cshtml` and `Shelf.cshtml`
   reduce editorial scaffolding and simplify browsing.

6. `FeatureDetail.cshtml`
   give live-proof, preview-concept, and roadmap detail pages visibly different structures.

7. `Home.cshtml` and `Account.cshtml`
   finish the signed-in split.

## Bottom line

The Hub does not need more concepts.

It needs:

- cleaner shell design
- less internal language
- stronger page editing
- calmer signed-in surfaces
- a short list of LTDs that improve proof, feedback, docs, screenshots, email, SEO, and demos without becoming the product itself
