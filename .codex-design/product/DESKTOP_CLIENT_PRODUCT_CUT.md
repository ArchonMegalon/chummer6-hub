# Desktop client product cut

## Purpose

Define the shipped desktop head, supported platform posture, and the minimum preview cut for the current desktop delivery wave.

## Shipped desktop head

### Flagship head

`Chummer.Avalonia` is the flagship desktop client for the current delivery wave.

It owns the primary native-shell preview, the default desktop UX posture, and the first recommended download path when a platform has a promoted desktop shelf.

### Head authority rule

`Chummer.Avalonia` is the flagship desktop client for the current delivery wave.

No second desktop head is currently part of the public preview shelf.

If a second desktop head is reintroduced later, it must earn its own install, workflow, update, and visual-familiarity proof instead of borrowing Avalonia trust.

### Gold-target head rule

A gold desktop claim is stricter than the current preview fallback story.

For gold:

* Avalonia may remain the default primary desktop route
* every shipped desktop head must independently satisfy the flagship bar
* a secondary head is not allowed to ship on thinner shell-only, visual-only, or borrowed proof

## Current preview cut

The desktop preview cut must feel like one coherent product, not a packaging demo.

The current minimum preview includes:

* builder and inspect flows
* explain and receipt-facing workbench surfaces
* import and export entry points
* account-aware install linking and first-launch claim handoff
* update check and release posture visibility
* crash, bug, and feedback entry points
* home/workspace continuity surfaces that let a claimed install continue where the user left off
* rule-environment activation, preset selection, and amend-package diff preview with proof of activation
* ruleset-authored builder and explain cues where SR4, SR5, and SR6 materially diverge

The preview cut must not present multiple desktop heads as equally primary to normal users.

## Flagship desktop bar

A public-ready desktop release is not only a successful binary build.

It must prove:

* one obvious flagship head on the public shelf
* Avalonia is the flagship head by default
* a secondary head never becomes the silent primary route
* a gold claim may keep one primary head, but every shipped head must independently clear startup, install, update, crash-recovery, feedback, workflow, and visual-familiarity proof
* startup, install, update, crash-recovery, and support flows that feel boring on the promoted path
* dense-data builder, compare, and explain flows that stay fast and readable under expert use
* the flagship shell still feels recognizably like Chummer to Chummer5a users: desktop menu, quick-action toolstrip, dense workbench center, and compact trust strip all survive in modern form
* authored SR4, SR5, and SR6 interactions where edition differences materially change the user's reasoning
* active ruleset, preset, and amend-package state that never turns rule drift into mystery local cargo
* import, claim, feedback, and release-help surfaces that agree with the public shelf and support truth

## Platform posture

### Windows

Windows is the primary promoted desktop preview lane.

The normal public CTA is installer-first. A portable `.exe` may be published as an advanced or support-directed fallback, but it must not outrank the recommended installer when the installer lane is healthy.

### Linux

Linux is the secondary desktop preview lane.

The target public install surface is installer-first through a `.deb` package, with bounded manual or archive-style fallback allowed only when support or platform reality still requires it.

### macOS

macOS remains buildable and design-supported, but it is not automatically public-promoted just because a build artifact exists.

Public promotion requires the codesign, notarization, and release-truth path to be complete enough that the shelf can make honest promises.

Until that gate closes:

* built `.dmg` artifacts count as internal release evidence, smoke evidence, and promotion-prep input
* public download manifests and public `/downloads` surfaces must not present macOS as currently available
* support copy must say that macOS availability depends on signed/notarized promotion, not on raw build success alone

## Artifact posture

The desktop wave distinguishes artifact roles explicitly:

* installer artifact: the recommended public install path for a promoted platform
* portable artifact: a support, advanced-user, or bounded fallback path that does not replace installer-first public posture
* machine update payload: the updater-consumable delivery unit used after install

Portable artifacts are valid product artifacts. They are not allowed to silently replace the recommended installer in public copy.

## Release rule

Desktop release truth must name the current flagship head explicitly.

If a second head ships later for the same platform:

* the public shelf must make one of them the obvious primary choice
* the release manifest must distinguish recommended versus secondary artifact posture
* support, update, and install-help copy must use the same distinction

## Current decision

For the current wave:

* flagship head: `Chummer.Avalonia`
* Windows public lane: installer-first with portable `.exe` fallback allowed
* Linux public lane: `.deb` first, bounded manual fallback allowed when the installer lane is not yet boring enough
* macOS lane: public only after signed/notarized `.dmg` promotion, startup-smoke proof, and release-truth close
