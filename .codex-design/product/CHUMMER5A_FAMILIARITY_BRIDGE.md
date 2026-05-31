# Chummer5a familiarity bridge

## Purpose

Modernizing Chummer6 must not erase the learned map that long-time Chummer5a users already carry in their heads.

This file defines the current-target bridge between flagship polish and legacy familiarity.

## Core promise

On the promoted desktop head, a Chummer5a user should feel "at home" within the first minute.
Install and first-run continuity must not break veteran orientation.

That means Chummer6 may modernize:

* contrast
* typography
* spacing discipline
* dark-theme quality
* recovery states
* platform fit

It must not casually discard the old workbench grammar.

## Familiarity cues that must survive

The flagship desktop shell must preserve these Chummer5a cues in recognizable form:

### 1. Classic top-level menu posture

The desktop shell keeps a real top menu with familiar desktop semantics.

Required:

* `File`
* `Tools`
* `Windows`
* `Help`

When the active workspace exposes edit or character-special actions, `Edit` and `Special` may appear between `File` and `Tools`, but they must behave like desktop menus rather than web nav tabs.

### 2. Immediate toolstrip under the menu

The next row under the menu must behave like a quick-action toolstrip, not a hero banner.

It should expose the veteran muscle-memory class of actions:

* new or home
* open or import
* save
* settings
* print or export where available
* support or report issue as bounded trust actions

### 3. Dense workbench center

The main body must still feel like a serious builder:

* left-side navigation or selected-item inventory
* central editing canvas
* dense summary and detail panes
* predictable right-side contextual inspector or command area where needed

It must not feel like a marketing dashboard wrapped around a form.

### 4. Bottom status strip with trust metrics

A compact bottom status strip must remain visible.

It should carry the modern equivalents of the old "always visible" cues:

* active character or workspace
* ruleset or build posture
* service or sync posture
* time or freshness
* one visible progress or readiness indicator

The exact metrics may evolve, but the feeling of "important state is always in the strip" must remain.

### 5. Tabbed or sectioned navigation rhythm

Character work should still read as a sequence of dense sections rather than an endless scroll of cards.

Required:

* sections are named and stable
* navigation stays visible while editing
* selection state is obvious
* the current section can be re-found instantly after a distraction

### 6. Workflow memory must survive, not only shell chrome

Veteran users do not just remember where the menu lives. They remember how to get work done.

Required:

* each Chummer5a workflow family that remains in product scope has a discoverable desktop equivalent
* the equivalent stays close enough in rhythm that a returning user does not have to relearn the whole builder from scratch
* parity is judged on executable flows, not on whether a tab or action id still exists
* deep builder cases such as modular cyberlimbs, subsystem-bearing implants, weapon accessory stacks, armor mod stacks, and vehicle mod flows are treated as audit oracles for whole-family trust

This is workflow-wide, not a shell-only promise. The same mental model should remain recognizable when the user is:

* creating a character
* spending karma and advancing an existing runner
* adding gear or armor
* adding drugs, consumables, and other temporary-effect items
* adding or editing cyberware and cyberlimbs
* configuring cyberdecks, programs, and other matrix gear
* configuring weapons and accessories
* working in adept powers, initiation/submersion, magic, or resonance sections
* working through spells, rituals, ally spirits, spirits/sprites, familiars, and related conjuring flows
* working through critter-specific creation or editing surfaces where that ruleset supports them
* editing vehicles, cars, drones, rigger surfaces, and mod trees
* moving through contacts, lifestyles, diary/career-log, notes, and other dense side workflows

The UI may modernize, but the user should still recognize the browse, inspect, confirm, and re-find rhythm from legacy Chummer.

### 7. Utility, reference, and settings families must get real successors

The bridge is not satisfied by shell chrome alone.

The flagship client must also preserve modern equivalents for the legacy utility and reference families that serious users depended on:

* sourcebook selection and sourcebook metadata editing
* master-index and rule-snippet lookup
* settings and character-settings posture
* custom-data, XML, and translator-era authoring bridges
* dice roller and initiative utilities
* character roster, watch-folder, and operator dashboards
* sheet viewer, print/export, and adjacent exchange lanes

These do not need to keep old window names or old layout quirks.

They do need one obvious, first-class modern route in the promoted client.

### 8. No MDI obligation

Chummer6 does not need a classic multi-document interface to honor legacy familiarity.

One-workspace tab posture is acceptable if:

* section rhythm stays obvious
* utility and reference lanes remain first-class
* users can move between active characters, utilities, and reference surfaces without getting lost

## Ruleset-specific orientation

The familiarity bridge is ruleset-aware.

### SR4

For SR4, Chummer4 remains a valid workflow-local oracle where it is the stronger legacy reference for that ruleset.

That means:

* the overall shell should still read as modernized Chummer
* workflow-local density can preserve older SR4-appropriate cues where that helps veteran users orient faster
* the point is not to flatten SR4 into SR5/SR6 chrome if that would make SR4 harder to use

### SR6

For SR6, the builder should feel familiar to a Chummer5a user even though the rules semantics differ.

That means:

* keep the same broad orientation model: menu, toolstrip, dense workbench, visible section rhythm, visible character tab posture
* adapt field sets, summaries, and rule-specific controls to SR6 instead of pretending SR6 is SR5
* preserve the familiar browse/detail/confirm cadence in workflow-local surfaces such as character creation, gear, augmentations, and rules-specific editors
* keep SR6 section landmarks stable and obvious, especially around:
  * attributes and qualities
  * skills
  * augmentation
  * gear
  * lifestyles, licenses, SINs, and contacts
  * character history / career log
* preserve helpful SR6-specific filtering and spend-mode posture, such as accessory filtering that narrows to compatible items and a visible choice between "buy/spend" and "add/manage" flows, but keep those aids inside the familiar Chummer browse/detail/confirm rhythm

SR6 should feel like "I know how to drive this" on first contact, not like an unrelated application with Shadowrun labels.

## Modernization rules

The bridge is not a pixel-perfect clone.

Chummer6 should improve on Chummer5a by:

* making dark mode actually legible
* reducing accidental clutter
* surfacing recovery and trust state explicitly
* keeping keyboard flow first-class
* making rule-environment posture visible
* making dense screens calmer without making them sparse
* keeping ruleset-specific builders recognizable without turning them into clones

## Anti-goals

The flagship desktop shell must not:

* replace the top desktop menu with a website-style nav bar
* replace the toolstrip with a large marketing hero
* hide essential state in overflow drawers or hover-only affordances
* turn dense builder work into oversized card stacks that waste vertical space
* remove the bottom status posture that veteran users rely on to stay oriented
* treat a framework-first installer choice as acceptable modernization on the promoted path
* force a decorative landing page before the workbench when a veteran expects to continue work immediately
* claim Chummer5a familiarity while leaving legacy workflow families stranded behind missing actions, shallow section placeholders, or inspection-only stubs

## Release implication

The flagship UI release gate must reject shells that are visually polished but no longer read as recognizably Chummer for Chummer5a users.
