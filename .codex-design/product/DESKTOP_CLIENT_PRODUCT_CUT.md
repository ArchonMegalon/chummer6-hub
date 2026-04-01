# Desktop client product cut

## Purpose

Define the shipped desktop head, fallback head, supported platform posture, and the minimum preview cut for the current desktop delivery wave.

## Shipped desktop heads

### Flagship head

`Chummer.Avalonia` is the flagship desktop client for the current delivery wave.

It owns the primary native-shell preview, the default desktop UX posture, and the first recommended download path when a platform has a promoted desktop shelf.

### Compatibility and fallback head

`Chummer.Blazor.Desktop` remains a compatibility and fallback desktop head.

It is still a real maintained delivery lane, but it is not the flagship product statement for the preview shelf. It exists to preserve parity, support bounded fallback cases, and keep the shared presentation seam honest while the flagship head matures.

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

* one obvious flagship head and one bounded fallback story
* startup, install, update, crash-recovery, and support flows that feel boring on the promoted path
* dense-data builder, compare, and explain flows that stay fast and readable under expert use
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

Desktop release truth must name one flagship head and one fallback story.

If both heads ship for the same platform:

* the public shelf must make one of them the obvious primary choice
* the release manifest must distinguish recommended versus fallback artifact posture
* support, update, and install-help copy must use the same distinction

## Current decision

For the current wave:

* flagship head: `Chummer.Avalonia`
* compatibility/fallback head: `Chummer.Blazor.Desktop`
* Windows public lane: installer-first with portable `.exe` fallback allowed
* Linux public lane: `.deb` first, bounded manual fallback allowed when the installer lane is not yet boring enough
* macOS lane: buildable but withheld from the public shelf until signed/notarized `.dmg` promotion and release-truth close
