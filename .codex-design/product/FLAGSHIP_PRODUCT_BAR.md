# Flagship product bar

## Purpose

This file defines what "flagship grade" means for Chummer.

It exists so whole-product quality is not reduced to "the tests passed" or "the milestone registry is empty."
`FLAGSHIP_RELEASE_ACCEPTANCE.yaml` is the machine-readable proof surface that operationalizes this bar.

## Core rule

A surface is not flagship grade just because it is feature-complete.
It is flagship grade only when the feature is:

* obvious to discover
* fast to use under real table pressure
* trustworthy when it explains itself
* visually and interaction-wise coherent with the rest of Chummer
* honest about limitations, preview posture, and recovery paths
* strong enough that a paying user would feel they received a deliberately crafted product rather than a successful internal tool

## Product-wide flagship promises

### 1. One obvious primary path per major job

Every major user intent must have one clear primary route:

* build a character
* understand a rule outcome
* compare options
* prepare or run a session
* recover from a crash or interrupted install
* publish or share an artifact

Fallback paths may exist.
They must not read like the real product while the primary path still feels provisional.

### 1b. Desktop familiarity must still read as Chummer5a

Desktop flagship quality is not satisfied by feature coverage alone.
The promoted desktop head must still read like Chummer to a veteran user:

* a real desktop menu
* first-class master index and character roster routes
* workbench-first startup instead of decorative landing chrome
* dense builder posture that feels like an instrument rather than a dashboard

For the remaining hard parity families, familiarity is judged by `CHUMMER5A_HUMAN_PARITY_ACCEPTANCE_SPEC.md` and `CHUMMER5A_HUMAN_PARITY_ACCEPTANCE_MATRIX.yaml`, not by aggregate desktop readiness alone.
If those families do not have direct dialog-level screenshot, runtime, and per-element verdict proof, the desktop head is not yet flagship grade.

Desktop familiarity is necessary but not sufficient.
The harder bar is whether a veteran user can move with the same:

* speed
* confidence
* reversibility
* inspectability
* trust under pressure

### 1c. Install and first-run experience must feel like one product

The promoted desktop path must behave like one coherent Chummer experience:

* guided product installer path first
* installer or in-app claim and recovery handling
* no browser ritual to copy or paste a claim code by hand
* first launch opens the real workbench or restore continuation flow

### 1a. Desktop head authority is explicit

`Chummer.Avalonia` is the default flagship desktop head for the current delivery wave.
`Chummer.Blazor.Desktop` is only a bounded fallback when the public shelf, platform matrix, and release evidence say so.
If Blazor is the only shipped desktop head for a lane or the recommended public route, it must meet the flagship bar directly instead of borrowing Avalonia proof.

### 2. Explainability and trust stay first-class

Flagship grade requires:

* explain receipts where the user expects "why?"
* bounded `why not?`, `what changed?`, and `what if I toggle this one factor?` answers on promoted explain surfaces
* visible state for conditional modifiers, active effects, and timed changes
* packet-backed source-anchor posture rather than folklore labels, detached citations, or presenter-only narration
* public release truth that matches the shelf, help copy, and install reality

The detailed explain contract lives in `EXPLAIN_EVERY_VALUE_AND_GROUNDED_FOLLOW_UP.md`.

### 2a. Trust, durability, and explainability outrank cosmetic similarity

Flagship grade fails when any of these are weak even if the shell looks familiar:

* update, rollback, restore, or first-launch trust
* character and campaign durability across migration or device change
* custom-data and amend-package survival
* large-sheet and dense-roster performance
* rule explainability where users ask "why?", "why not?", or "what changed?"

Those planes are machine-tracked in `FLAGSHIP_READINESS_PLANES.yaml`.

### 3. SR4, SR5, and SR6 must feel authored, not flattened

Ruleset support is not done when one lowest-common-denominator form can technically enter the data.

Flagship grade requires:

* deterministic parity in engine truth
* ruleset-specific terminology where the editions materially differ
* ruleset-specific interaction affordances where a shared generic workflow would feel confusing or lossy
* import and migration proof that catches silent rules drift

### 4. Dense data must feel comfortable at expert speed

Chummer is a power-user product.
Flagship grade therefore requires:

* grouped inspection instead of long flat walls of state
* fast compare and scan behavior
* cancel-safe editing for high-risk multistep flows
* visible timelines where training, downtime, travel, or temporary effects matter

### 5. Recovery must be boring

Users must be able to survive:

* app crashes
* update failures
* broken downloads
* device changes
* reconnect/replay situations

without losing trust in the product.

Recovery also fails when the product tells different stories in different places.
Installer bytes, release-channel truth, public shelf truth, in-app update truth, and support truth must agree or the release is not flagship grade.

### 6. Imports must respect prior investment

Legacy Chummer and adjacent import lanes are not only migration helpers.
They are also quality oracles.

Flagship grade requires:

* respectful import of legacy user state where the product promises parity
* explicit receipts when an import is partial, lossy, or blocked
* regression and oracle tests that compare imported source facts against Chummer6-derived outcomes

### 7. Rule environments must be explicit and portable

Flagship grade requires:

* the active ruleset, preset, and amend package set are visible where users build, explain, import, restore, and compare
* package activation has preview, diff, dependency, and rollback posture instead of ambient custom-data magic
* missing, incompatible, or downgraded packages are explicit before the product computes against the wrong environment
* the amend-package family is strong enough to support current custom-data needs and later governed promotion without inventing a second representation

### 8. Public surfaces must feel premium and honest

`chummer.run`, downloads, guides, help, and artifact shelves must feel like a deliberate product front door:

* polished enough to create trust
* bounded enough to avoid overclaiming
* aligned enough that install, update, help, and support routes never contradict each other

### 8a. Public proof, preview, fallback, and flagship claims stay distinct

Public trust language must keep four different promises separate:

* proof shelf language can say what was posted, recently checked, and inspectable today
* preview language can invite real use without implying flagship completeness
* fallback language must name backup, recovery, or compatibility posture explicitly and must not read like the recommended route
* flagship language is reserved for surfaces that independently clear `FLAGSHIP_RELEASE_ACCEPTANCE.yaml`

When those promises appear on the same page, the install shelf remains the authority for what to start with.
Proof cards, artifact explainers, captions, preview siblings, and packet-detail artifacts can support that page, but they must stay visibly secondary to the recommended route.

Artifact-factory cards, preview siblings, captions, explainers, and packet-detail artifacts can make the product more inspectable.
They do not by themselves turn a preview lane or fallback route into a flagship promise, and they do not become substitute route authority for the public install shelf.

### 9. Surface design must be systematized, not improvised

Flagship grade requires a shared cross-surface design contract.

That contract lives in `SURFACE_DESIGN_SYSTEM_AND_AI_REVIEW_LOOP.md` and is mandatory for:

* desktop workbench
* mobile/play shell
* Hub and support surfaces
* public landing, downloads, and guides
* artifact preview and publication surfaces

Flagship grade therefore requires:

* one shared token and state language across heads
* platform-respectful layouts instead of lowest-common-denominator reuse
* dark and light themes that are both trustworthy
* screenshot-based critique and revision before promoted UI changes are accepted

## Repo implications

### `chummer6-core`

* deterministic rules, import, explain, and parity proof must be strong enough that UI polish is not hiding mechanical uncertainty

### `chummer6-ui`

* workbench and desktop surfaces must feel premium under heavy use
* SR4/SR5/SR6 differences must get authored UX where the editions meaningfully diverge

### `chummer6-mobile`

* play-shell continuity, reconnect, and tablet/mobile comfort must feel trustworthy during live play, not just in happy-path demos

### `chummer6-hub` and `chummer6-hub-registry`

* landing, account, downloads, publication, install guidance, and support/control surfaces must feel like one product

### `chummer6-ui-kit`

* shared tokens, dense-data primitives, accessibility, and localization posture must enable flagship-quality work across heads
* shared implementation substrate must make `SURFACE_DESIGN_SYSTEM_AND_AI_REVIEW_LOOP.md` cheap to apply instead of leaving every head to reinvent quality locally

### `chummer6-media-factory`

* artifact outputs, previews, and manifests must feel polished enough to justify publication and recap surfaces as true product lanes

### `fleet` and `executive-assistant`

* the loop must keep decomposing and proving full-product work instead of confusing wave closure with whole-product completion

## Release consequence

Public release is not truly complete until flagship bar evidence exists for:

* desktop build, startup, and support reality
* rules parity and import confidence
* explicit rule-environment and amend-package honesty
* cross-surface design authorship and screenshot-backed quality proof
* mobile play continuity
* public/download/help honesty
* artifact and publication credibility
* operator and support loop trust

Release proof must also classify intentional divergence explicitly:

* `must_match`
* `may_improve`
* `may_remove_if_non_degrading`

That evidence must compile into `FLAGSHIP_RELEASE_ACCEPTANCE.yaml` rather than remaining only prose or operator intuition.
