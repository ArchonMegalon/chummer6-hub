# Public auto-update policy

## Purpose

Chummer should install like a serious desktop product and stay current like one.

Normal users should not need to revisit a download shelf for every release.
The expected product posture is:

* install once
* stay on a visible update channel
* receive signed update metadata
* apply the next release through the installed app

## Primary rule

Public desktop releases should support channel-aware auto-update.

That means:

* Windows installer lanes should support in-app update discovery and apply flow.
* macOS installer lanes should support in-app update discovery and apply flow.
* Linux desktop lanes should support an updater story where the package/runtime allows it, or otherwise make channel ownership and package-manager update posture explicit.

Portable archives do not count as the primary update experience.

## User experience rule

The installed product should make update posture legible without turning the app into an updater console.

At minimum, the user should be able to see:

* current version
* current channel
* whether an update is available
* the next action to apply it

The preferred experience is:

* background check
* quiet “update available” moment
* explicit install/apply action
* restart when required

The updater should feel like product maintenance, not release archaeology.

## Channel rule

Auto-update must be channel-aware.

The product may expose multiple channels, but the rule is:

* stable is the default public lane
* preview or beta lanes are explicit opt-ins
* channel changes are deliberate, visible, and reversible where supported
* the product must not silently move users between channels

Downloads, settings, and release notes should all agree on the same channel names.

## Integrity rule

Update metadata and payload selection must be integrity-checked.

The public design bar is:

* signed or equivalently verifiable update metadata
* package integrity visible to the operator/publisher layer
* no unsigned opaque update swap hidden behind the UX
* failure states that prefer “stay on current version” over risky apply behavior

Update convenience does not overrule release trust.

## Installer rule

Installer-first packaging and auto-update belong to the same public story.

That means:

* the main desktop download should be an installer/setup package
* the installed app should own future release discovery
* manual archives live in an advanced/manual lane only

If the product still requires most users to download a fresh ZIP for routine updates, the packaging posture is below bar.

## Downloads rule

`/downloads` should explain both install posture and update posture.

The page should make it easy to understand:

* which installer/setup package to use
* which channel it joins
* whether that package supports auto-update
* where manual/archive formats live

Checksums remain visible, but the emotional center of the page is install-and-stay-current, not archive collection.

## Settings rule

Signed-in or installed product surfaces may later show update settings, but they should stay compact.

Good settings language looks like:

* Update channel
* Check for updates
* Update available
* Restart to finish update

Do not turn normal settings copy into updater plumbing, feed URLs, or package-manager jargon.

## Ownership

* `chummer6-design` owns the public update posture and user-language bar.
* `chummer6-hub` owns the hosted projection of install/update posture on `chummer.run`.
* packaging and release-manifest owners must surface enough metadata for Hub and installed clients to present channel/update truth cleanly.
