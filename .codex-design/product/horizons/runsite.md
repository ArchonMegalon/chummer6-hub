# RUNSITE

## Explanation video

[Watch the RUNSITE 90-second deep dive](https://chummer.run/media/horizons/runsite-90s-deepdive.mp4). [Captions](https://chummer.run/media/horizons/runsite-90s-deepdive.vtt).

## The problem

GMs spend too long describing spaces, and players still misread compounds, clubs, hotels, museums, arcologies, and safehouses once the action starts.

## What it would do

Chummer would publish explorable location packs linked to mission briefings.
They could include floor plans, hotspots, route overlays, optional narration, and static map context, but they stay focused on helping you understand the space before the run starts, not on replacing live combat tools or a VTT.
RUNSITE is for briefing, planning, and spatial understanding before things go loud.

## Likely owners

* `chummer6-hub`
* `chummer6-media-factory`

## Key tool posture

* `Crezlo Tours` - primary explorable-tour lane
* `AvoMap` - route and location visualization support
* `PeekShot` - preview/share-card adapter
* `vidBoard` - bounded orientation-host and walkthrough clip lane
* `Soundmadeseen` - optional narration layer
* `BrowserAct` - bounded operator automation and capture fallback

## What has to be true first

* clean media manifests
* permissioned publication links
* preview and embed receipts
* reliable map and render adapters

## What is ready now

RUNSITE is now a shipped first-party prep lane.
The public rail exposes real runsite packs on markdown and JSON routes plus a named receipt at `/runsites/receipts/prep-network.json`.
The signed-in rail is no longer generic workspace spillover; it has a named bench at `/account/runsites`, a named redirect lane at `/account/runsites/open`, and workspace detail routes at `/account/runsites/{workspaceId}`.
Typed prep and run APIs are first-class too:

* `/api/v1/campaign-spine/me/workspace-digests`
* `/api/v1/campaign-spine/me/workspaces/{workspaceId}`
* `/api/v1/campaign-spine/me/workspaces/{workspaceId}/prep-library`
* `/api/v1/campaign-spine/me/runs`
* `/api/v1/campaign-spine/me/runs/{runId}`

## Refined spatial premiere loop

RUNSITE should present each strong pack as a spatial premiere, not a static download:

* Route truth first: the GM and players see the approved pack summary, route notes, hazards, and inspection links before any media plays.
* Explorable sibling second: the pack can expose a tour or route-visualization companion when the media manifest and publication links are verified.
* Host layer third: a short orientation clip or narration can sell the space before play, but it must always point back to the route and tour truth.
* QA and confidence fourth: responsive screenshots, accessibility checks, crawl health, metadata, and public visibility reviews support the route without becoming product truth.
* Analytics last: public engagement can be measured through sanitized route, CTA, and tour-entry events only; no campaign text, player data, route secrets, or private runner identifiers are analytics payload.

The current LTD inventory supports this without inventing a new public provider promise:

* `Crezlo Tours`, `AvoMap`, and `PeekShot` remain the direct spatial artifact lanes for explorable tours, route visuals, and preview cards.
* `Subscribr` can draft approved-source orientation scripts, hooks, descriptions, and thumbnail briefs for RunSite clips, but publication approval stays Chummer-owned.
* `Rafter` and `Pixefy` can provide auxiliary live-site, accessibility, responsive screenshot, and visual QA evidence for RunSite pages and embedded tour surfaces.
* `ClickRank` and `NeuronWriter` can surface crawl, metadata, schema, internal-link, and source-packet SEO opportunities for `/runsites`, but accepted changes must patch Chummer-owned source first.
* `Rybbit` can measure sanitized public funnel events such as pack opened, tour opened, receipt opened, and account bench CTA clicked.

Public RunSite copy must describe the user value as "walk the job before the team walks into it." Provider and LTD names stay internal unless a specific page is explicitly documenting the operating model.

## Boundary

RUNSITE is a prep and orientation lane.
It does not claim tactical authority, live-map truth, or VTT replacement status. Route overlays, tours, and host clips stay subordinate to first-party workspace and run truth.
