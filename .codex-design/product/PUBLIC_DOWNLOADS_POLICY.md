# Public downloads policy

## Purpose

`/downloads` is the public install shelf for Chummer.
It should feel like a trustworthy software distribution surface, not a raw artifact dump.
It is the public install-and-update shelf, not a ZIP archive browser.

## Primary rule

Public desktop downloads should be installer-first.

That means:

* Windows should prefer a signed setup experience such as `.msi` or installer `.exe`.
* macOS should prefer `.dmg` or `.pkg`.
* Linux should prefer an installable desktop format such as `AppImage`, `deb`, or `rpm` when that lane exists.

Portable archives such as `.zip` or `.tar.gz` may exist, but they are fallback/manual formats rather than the primary product promise.

## Product bar

The public front should present Chummer as an installable desktop product.

That means:

* landing and start-here copy should point at installers, not generic build archives
* the main public action should be `Download installer`
* ZIP and tarball formats are advanced/manual escape hatches

If installer packages are absent, the release posture is below the design bar rather than the desired steady state.

## Presentation rule

The downloads page should present one clean install shelf:

* current version
* channel
* publish date
* platform
* package kind
* update behavior
* size
* checksum
* primary install/download action

Checksums remain visible beside every public package.
Channel and update behavior should be legible beside the package, not buried in release notes.

## Demotion rule

Archives should not be the hero action once installer packages exist.

If `.zip` or `.tar.gz` builds remain necessary, they should live under a quieter advanced/manual lane such as:

* Other formats
* Manual install
* Portable archive

They do not become the emotional center of the public install story.

## Manifest rule

Public release manifests should distinguish package kind and update posture, not only filename and platform.

At minimum, the product surface should be able to tell the difference between:

* installer
* auto-updating installer
* portable archive
* advanced/manual package
* update channel

The front door should not force users to infer install posture or updater behavior from filenames alone.

## Landing rule

Landing and start-here CTAs should point to `/downloads`, and the public posture is installer-first:

* use `Download installer`
* explain channel and update behavior on the downloads page
* do not center generic `current build` language in the public product story

## Ownership

* `chummer6-design` owns the public packaging posture.
* `chummer6-design` also owns the update posture described in `PUBLIC_AUTO_UPDATE_POLICY.md`.
* `chummer6-hub` owns the hosted projection on `chummer.run`.
* publication/manifest owners must surface enough metadata for the front to present installer versus archive truth cleanly, including update-channel behavior where relevant.
