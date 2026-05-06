# Localization and language system

## Purpose

Define locale ownership, string-domain boundaries, runtime language behavior, fallback rules, translator workflow, and acceptance gates for the current Chummer desktop and hosted surfaces.

## Shipping locale set

The phase-1 shipping locale set is locked to the carried-forward Chummer5a language corpus:

* `en-US` as source and fallback locale
* `de-DE`
* `fr-FR`
* `ja-JP`
* `pt-BR`
* `zh-CN`

This preserves continuity for migration, translators, support expectations, and the carried corpus already present in the current UI repo.

## Ownership split

`chummer6-design` owns locale scope, domain boundaries, fallback rules, and acceptance gates.

`chummer6-ui` owns desktop and workbench localization runtime behavior, translation ingestion, missing-key handling, and localization-safe release gating for desktop surfaces.

`chummer6-mobile` owns the corresponding runtime behavior for mobile and session surfaces.

`chummer6-core` owns explain, receipt, and rules-facing text contracts when those strings are emitted from engine or runtime truth.

## Translation domains

The localization system must preserve at least these domains:

### App chrome

Shell chrome, navigation, settings, install/update/support entry points, dialogs, and bounded product copy.

### Explain and receipt text

Grounded explain output, receipts, migration explanations, updater state text, and support/status language that is generated from truth-bearing product actions.

### Data and rules names

Rules, catalog, and data-facing labels that historically came from the Chummer language corpus and its paired data-localization files.

### Generated artifact text

User-visible generated output that leaves the immediate UI shell, such as exported sheets, visible update/help packets, or bounded release/support projections.

This domain also includes campaign cold-open and mission-briefing siblings:

* captions
* preview copy
* primer packets
* mission packets
* explicit text fallbacks when localized media is unavailable

It also includes Build and Explain companion siblings:

* narrated compare summaries
* import-followthrough captions and text fallbacks
* blocker companion captions and text fallbacks
* receipt-anchor labels and inspectable sibling actions

It also includes rule-environment grounded-media siblings:

* activation-receipt labels
* diff-receipt labels
* rule-environment badges
* localized text fallbacks for campaign-drift, restore, import, and support follow-through companions

### Companion runtime text

First-party companion barks, action chips, evidence-drawer labels, voice opt-in copy, and rare scene fallback text that render inside desktop or mobile runtime surfaces.

## Authoring source

The carried XML language corpus remains the translation authoring source for the current desktop wave.

That means:

* keep the legacy `lang/*.xml` and `lang/*_data.xml` split as the authoring truth for now
* keep the existing Translator app and related tooling as the practical authoring path during this wave
* add bridge layers in modern heads instead of demanding a full resource-format rewrite before the desktop preview is credible

Reformatting the translation corpus is an additive later step, not a prerequisite for shipping the current desktop wave.

## Runtime behavior

Phase 1 runtime language behavior is intentionally boring:

* language is chosen in Settings
* changing language requires restart
* unsupported or malformed locale codes fall back to `en-US`
* numbers, dates, and similar culture-sensitive formatting follow the chosen locale when supported
* missing keys must not silently create mixed-language public surfaces
* companion text, chips, evidence drawers, and voice-mode affordances must resolve in the chosen locale
* campaign cold-open and mission-briefing launch labels, captions, preview cards, and sibling packet copy must resolve through one deterministic locale chain
* Build and Explain companion launch labels, captions, preview cards, and inspectable sibling actions must resolve through one deterministic locale chain
* artifact shelf labels, captions, packet siblings, retention badges, and inspectable sibling actions must resolve through one deterministic locale chain
* if EA compile output, a companion locale pack, or a media attachment is unavailable, runtime falls back to the first-party local template for that locale and then to `en-US`
* denied or unavailable microphone access keeps the same localized text-first path instead of hiding actions or surfacing ad hoc English prompts

Campaign artifact locale fallback is:

1. requested user locale
2. campaign default locale
3. `en-US`

Locale fallback may degrade presentation polish.
It may not widen spoiler scope, change audience class, or silently mix translated and untranslated campaign artifact siblings.

For Build and Explain companions, locale fallback also may not drop receipt-anchor labels, paraphrase away blocker severity, or replace inspectable packet references with freer narration.
It also may not swap packet revision ids, approval-state labels, or rule-environment badges for locale-specific marketing copy that makes the artifact look more final than the underlying receipt truth.

For rule-environment grounded-media companions, locale fallback also may not paraphrase away activation or diff receipt identity, collapse active-versus-compared environment posture, or replace the required text-first recovery action with freer presenter phrasing.

For artifact shelves, locale fallback also may not hide audience posture, retention posture, inspectable sibling actions, or source packet identity behind smoother localized marketing copy.

If a locale or string is unavailable, the product must fall back deterministically to `en-US` instead of rendering ad hoc partial state.

## Missing-key policy

The current delivery rule is fail-fast for product chrome that would otherwise hide broken localization posture.

That means:

* critical install, update, support, and settings surfaces must surface missing-key diagnostics in development and release gating
* explain and receipt text may degrade to the canonical fallback string only when the product can still remain honest about what happened
* public-facing trust, install, and support surfaces must not silently blend untranslated and translated strings in ways that look complete when they are not
* companion runtime may not wait on EA compile, media lanes, or speech services; it must render the first-party fallback copy or stay silent when the trigger is no longer relevant

## Support-critical scope

Localization is not limited to the workbench.

The following surfaces are first-class localization scope from day one of the desktop wave:

* downloads and install guidance
* first-launch claim and account-aware install linking
* first-run companion greeting and voice opt-in prompt
* update status and release posture
* crash capture and recovery
* bug reporting
* lightweight feedback
* support status and closure messaging
* restore-conflict, campaign-drift, and fix-confirmation companion moments

If those surfaces remain English-only while the rest of the app looks translated, the product trust loop is not actually localized.

## Acceptance gates

Localization readiness requires:

* pseudo-localization coverage for desktop chrome
* missing-key fail-fast checks in release validation
* screenshot or visual overflow checks for top desktop surfaces
* locale smoke tests for first launch, companion cards, settings, build sheet, explain panel, updater surfaces, and support dialogs
* voice-opt-in fallback smoke proving the companion stays truthful when microphone permission is denied or when EA/media lanes are unavailable
* at least one generated-artifact smoke in a non-English locale

## Current phase rule

The current desktop delivery wave should bridge the existing XML corpus into the flagship desktop head instead of rewriting localization architecture from zero.

The quality bar is:

* explicit supported locale set
* deterministic fallback
* restart-safe language changes
* localized install/update/support surfaces
* localized companion runtime copy with deterministic text-only fallback
* release gating that proves the localization system is not drifting silently
