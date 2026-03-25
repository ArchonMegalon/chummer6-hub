# Install and update

Status: early_access_preview

## User goal

Choose the right build, install it, and later update it without guessing which channel or runtime bundle is real.

## Entry surfaces

* `chummer.run/downloads`
* Hub account-aware install surfaces
* Registry-backed release and compatibility records

## Happy path

1. The user opens the public or signed-in download shelf.
2. Hub reads registry truth for promoted channels, installer records, and compatibility facts.
3. The user selects the installer that matches head, platform, architecture, and channel.
4. The installed UI head uses registry-owned update truth when checking for updates.
5. Follow-up updates preserve the same registry-backed compatibility story.

## Failure modes

* If a promoted head lacks compatibility or runtime-bundle metadata, the download route must block or clearly label the gap.
* If updater behavior and registry channel truth disagree, registry wins and the mismatch is release-blocking.
* If a build is still preview quality or otherwise rough-edged, the shelf must say so plainly instead of implying stable general availability.

## Success evidence

* Installer, channel, platform, architecture, runtime-bundle head, and compatibility data stay coherent end to end.
* Hub does not invent release truth locally.
* UI owns installer and updater behavior without reclaiming registry authority.

## Canonical owners

* `chummer6-hub`
* `chummer6-hub-registry`
* `chummer6-ui`
* `fleet`
