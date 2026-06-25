# RunSite Story: Chummer Run Web Desktop, LTD Dossiers, and Self-hosting

## Purpose

RunSite is the public web front door for Chummer Run. It should explain, demonstrate, and launch the browser-hosted Chummer experience while making Docker self-hosting feel like a supported product path, not an afterthought.

The page should feel less like a marketing site and more like the public lobby for an operational web desktop: launch the client, inspect location dossiers, understand self-hosting, and trust the privacy boundaries before entering.

This file is the implementation handoff for the RunSite codebase. Another Codex/session should implement from this file without needing the prior chat.

## Product Thesis

Chummer Run should feel like a full web-delivered desktop environment:

- Blazor is a first-class Chummer client, not a reduced companion app.
- Chummer Run hosts the web client, persistence, auth/session flow, public launch surfaces, and operator-facing deployment story.
- Users can choose hosted Chummer Run or self-host the same stack in Docker.
- The newest LTD/license entries become premium demo content and campaign-location material.
- Rybbit provides lightweight funnel visibility for public RunSite and hosted launch flows without making analytics mandatory.

Core user story:

> I can visit RunSite, understand that Chummer now runs as a polished browser desktop, launch it, inspect immersive location demos, and decide whether to use hosted Chummer Run or deploy it myself.

## Audience

- Players who want a browser-accessible Chummer client.
- GMs who need campaign locations, rosters, and hosted table workflows.
- Self-hosters who want Docker-first deployment with explicit privacy controls.
- Operators who need a public site that can show health, launch paths, tour demos, and analytics-backed conversion.

## Core Narrative

RunSite should present Chummer Run as an operations console for tabletop campaigns:

1. Start with the web desktop promise.
2. Prove parity with the existing desktop client workflow.
3. Show the newest LTD/location license entries as campaign-ready dossiers.
4. Offer self-host Docker as a first-class path.
5. Expose Rybbit-powered insight only as lightweight operational telemetry, never as a dependency.

## Page Structure

### 1. Hero: Run Chummer Anywhere

Primary copy:

> A full Chummer client in the browser, hosted on Chummer Run or self-hosted in Docker.

Primary CTAs:

- `Launch Web Client`
- `Self-host with Docker`
- `Explore 3D Tour Dossiers`

Hero composition:

- Left side: strong product statement and CTAs.
- Right side: layered mock console showing character roster, campaign workspace, and a highlighted property-tour dossier.
- Background: tactical parcel grid, blueprint lines, subtle route/path traces.
- The browser client must feel like another desktop client. Avoid preview/demo-only language unless the current implementation genuinely requires it.

### 2. Web Desktop Parity Strip

Purpose: make clear that the Blazor client follows the Avalonia/user workflow, translated for web.

Content points:

- Character roster remains the starting point.
- Users can organize characters into custom roster directories and a nested hierarchy of their choosing.
- Drag-and-drop roster movement should feel like file management in a desktop client.
- Campaign/session state should feel persistent and local-first even when hosted.
- The browser workbench should expose launch, roster, editor, GM workflow, and export paths as one coherent desktop-like surface.

Copy direction:

> Same Chummer workflow. Browser delivery. Hosted or self-hosted.

Implementation notes:

- Link to the Blazor/web-client design spec and parity docs when routes are available.
- Treat this as a product promise, not just technical documentation.

### 3. LTD Dossier Board

Purpose: turn the newest LTD license entries from `EA LTDs.md` or the active LTD license source into a distinctive RunSite showcase.

The section should not be a normal gallery. It should feel like a mission-board/property-intelligence wall.

Design concept: `Location Dossiers`

Each dossier card should include:

- Location/property title from the newest LTD entries.
- License category from the source entry.
- Use case: safehouse, campaign base, office, warehouse, venue, public demo, lead magnet, meet site, or run target.
- Status chip: `Demo-ready`, `Campaign-ready`, `Private license`, `Needs embed`, or `License-only`.
- Preview frame, embed, map treatment, or placeholder based on what the newest license entry actually supports.
- CTA: `Open Tour`, `Use as Campaign Location`, or `Request Hosted Demo`.

Preferred layout:

- Left rail: filters for license type, location use, and availability.
- Center: large active tour preview with blueprint/map treatment.
- Right rail: dossier metadata, licensing notes, and conversion CTA.
- Bottom rail: compact carousel of additional dossiers.

Data rule:

- Seed cards from the newest LTD/license entries in `EA LTDs.md` or the active LTD license source, not from invented placeholder properties.
- Prefer the newest entries even if they are not 3D-tour embeds. Do not fall back to older tour-shaped entries just because they are easier to present.
- If the newest entries are license-only, render them as `License-only` dossiers with a clear next step instead of pretending an embed exists.
- If embeds are not yet available, render intentional placeholders that explain the missing integration state.
- Do not expose private/license-sensitive details beyond what the license source already marks as safe for public use.

Suggested dossier modes:

- `Live Tour`: embedded or directly linked 3D tour is available and public-safe.
- `Campaign Location`: license is usable as a table location but does not have a live public embed yet.
- `Private Asset`: source indicates restricted/private usage; show only safe metadata or omit from public output.
- `Operator Lead`: useful for sales/demo routing; show a request-demo CTA rather than a public asset link.

### 4. Self-host Docker Section

Purpose: make self-hosting feel real, safe, and maintained.

Content points:

- Hosted Chummer Run is the quickest path.
- Docker self-hosting is explicitly supported.
- Configuration is `.env` driven.
- Rybbit is optional and can be disabled or pointed at a self-hosted analytics instance.
- Blazor client, run services, persistence, and portal routes should be represented as one deployment story.

CTAs:

- `Copy docker compose`
- `Download .env template`
- `Read self-host guide`

Implementation details:

- Do not expose secrets from the real `.env`.
- Provide a sanitized `.env.example` or docs route.
- If copy/download helpers are not implemented yet, render disabled CTAs with clear `Coming soon` labels instead of dead links.

### 5. Rybbit Analytics Integration

Purpose: measure public RunSite conversion without making analytics required.

Minimum events:

- `runsite.hero.launch_web_client`
- `runsite.hero.self_host_docker`
- `runsite.hero.view_3d_tours`
- `runsite.blazor.launch`
- `runsite.self_host.copy_compose`
- `runsite.self_host.download_env`
- `runsite.tour.open`
- `runsite.tour.request_demo`
- `runsite.docs.open_parity_spec`
- `runsite.docs.open_self_host_guide`

Suggested environment variables:

```env
RYBBIT_ENABLED=false
RYBBIT_SITE_ID=
RYBBIT_SCRIPT_URL=
```

Analytics contract:

- Gate script injection behind `RYBBIT_ENABLED` plus configured site id/script URL.
- Missing Rybbit config must not break rendering.
- Event helper must no-op when analytics is disabled.
- Track route/workflow metadata only.
- Do not track character names, private campaign content, sheet data, secrets, or self-host operator env values.
- Public RunSite analytics can be enabled by default in hosted deployment only when the hosted operator explicitly configures it.
- Docker/self-host analytics should default to disabled unless the operator opts in.

### 6. Operator/Admin Teaser

Purpose: hint that Chummer Run is operationally managed without turning the public page into an admin console.

Cards to show:

- Public status.
- Web client availability.
- Hosted workbench route.
- Self-host docs status.
- Tour dossier availability.
- Rybbit configured/not configured.

This can later become an authenticated dashboard, but the public page should only show safe aggregate or static status.

## Visual Direction

Use a `property intelligence console` identity:

- Slate, ink, bone, map-paper, and amber palette.
- Blueprint grid overlays and parcel boundary lines.
- Dossier cards that look like tactical case files, not generic SaaS cards.
- Strong typography with a technical/editorial feel.
- Layered panels with purposeful depth.
- Subtle motion: dossier reveal, active-tour panel shift, CTA trace-line animation.

Avoid:

- Generic purple SaaS gradients.
- Plain Bootstrap/admin-dashboard styling.
- Treating 3D tours as ordinary image thumbnails.
- Hiding self-hosting below the fold as a secondary concern.

## Character Roster Hierarchy Story

RunSite should mention and link into the Blazor roster hierarchy work because it is a major desktop-parity proof point.

Desired user workflow:

- A user opens the web client and sees a character roster that behaves like a desktop file tree.
- The user can create custom roster directories and nested directories.
- Characters can be dragged into directories or between directories.
- Directory hierarchy is user-defined, not hardcoded by campaign/source/status.
- The tree should support keyboard-accessible movement as a non-drag fallback.
- Search/filter should preserve hierarchy context instead of flattening everything into an anonymous result list.

RunSite copy should summarize this as:

> Organize runners your way: custom directories, campaigns, safehouses, crews, or any hierarchy that matches your table.

RunSite should not promise filesystem mutation. This is web-client roster organization unless the Blazor/client docs later define an explicit filesystem export/import behavior.

## Implementation Tasks

1. Locate the RunSite frontend entry point in this codebase.
2. Build the landing composition around hero, parity, LTD dossiers, self-hosting, analytics insight, and operator teaser sections.
3. Add environment-driven Rybbit script injection.
4. Add a tiny analytics event helper with no-op fallback.
5. Wire CTAs to analytics events where available.
6. Seed dossier data from the newest LTD license entries.
7. Add intentional empty/loading states for tour embeds that are not implemented yet.
8. Add self-host Docker CTAs using sanitized examples only.
9. Link Blazor parity/design docs and self-host docs when routes exist.
10. Keep all copy explicit that hosted and self-hosted are both supported paths.
11. Include the roster hierarchy story as a desktop-parity feature, but keep actual roster implementation in the Blazor client.
12. If the newest LTD entries are not public-safe, add an operator-only placeholder state instead of leaking details.

## Acceptance Criteria

- RunSite clearly positions Blazor as a first-class browser desktop client.
- The hero has launch, Docker self-host, and tour dossier CTAs.
- The page explains desktop parity and user workflow continuity.
- The page includes a visible self-host Docker path with sanitized config guidance.
- Rybbit can be enabled for hosted RunSite without breaking self-host deployments.
- Analytics no-op cleanly when disabled or unconfigured.
- No private `.env` values, character data, or campaign content are exposed.
- LTD dossier cards are based on real newest license entries or explicit non-live placeholders.
- The visual identity feels like a property intelligence console, not generic SaaS.
- The next implementer can start from this file alone and find the intended sections, events, and data rules.

## Boundaries

- Do not implement Blazor roster hierarchy inside RunSite. RunSite should market/link that capability.
- Do not invent property names when real LTD entries are available.
- Do not skip the newest LTD/license entries merely because older entries are easier to render as tours.
- Do not make Rybbit required for rendering or self-hosting.
- Do not expose real `.env` secrets.
- Do not block public launch CTAs on tour embed readiness.
