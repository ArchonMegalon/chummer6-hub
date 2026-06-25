# RunSite Handoff: 3D Tour, Rybbit, and Chummer Web Client Positioning

## Objective

Implement the RunSite/chummer.run landing and product-site ideas around the newest LTD/license assets, Rybbit, and the 3D tour angle. This is separate from the current Blazor Character Roster hierarchy work in `chummer-presentation`.

## Starting context

- The active Blazor thread has been working on web-client parity, especially Character Roster hierarchy.
- RunSite work was discussed but not implemented in that thread.
- Before implementing, inspect the newest entries in `LTDs.md` and `.env`.
- Do not rely on older LTD assumptions. The user explicitly corrected prior assumptions with: "look at the newest entries", ".env", and "there is more the ltd licenses".
- Do not hardcode secrets from `.env` into committed files.

## Product/design direction

Make RunSite benefit from the new 3D tour LTDs acquired for PropertyQuarry.

Treat the 3D tour tooling as a reusable interactive showcase capability, not just a real-estate tool. For chummer.run, use it to sell the web client as a live, explorable desktop-in-browser experience.

Recommended concept: **Tour the runner desk**

- A 3D/interactive product tour where users walk through the Chummer web workspace.
- Hotspots for Character Roster, runner tabs, GM/table handoff, import/reconcile, rules citation, offline/cache, Docker self-hosting, and privacy/Rybbit.
- Each hotspot opens concise product copy plus a CTA.
- For self-hosters, include "Docker cockpit" hotspots covering env vars, volumes, backups, and analytics opt-in.

## 3D tour implementation paths

- If the LTD/provider supports embeds, add a polished tour embed on RunSite.
- If it only supports hosted external links, add a first-class "Interactive Tour" section linking out.
- If API/automation exists, model tours as release artifacts that can be regenerated or updated.
- If provider capability is unclear, implement a strong fallback section with screenshot-style cards and hotspot copy, then leave provider-specific wiring behind env/config.

## Rybbit

Enable Rybbit on chummer.run / RunSite if not already done.

Rules:

- Keep privacy posture explicit.
- Prefer anonymous aggregate analytics language.
- Do not add invasive tracking.
- Wire from env only.
- If `.env` contains Rybbit host/site IDs/tokens, use those names via configuration, not literals.
- Add placeholder env docs/comments for required vars.

Suggested env names if none already exist:

```env
RYBBIT_ENABLED=false
RYBBIT_HOST=
RYBBIT_SITE_ID=
RYBBIT_SCRIPT_URL=
```

## Landing-page structure

Hero:

- Headline: "Chummer, as a desktop-grade web client."
- CTAs: "Open Web Client", "Self-host with Docker", "Take the Interactive Tour".

Section: Desktop workflow, browser reach

- Avalonia workflow parity
- Character roster
- Import/open/save/export
- GM/table tools
- Rules/source citations

Section: Tour the runner desk

- 3D tour embed or hosted link
- Hotspot cards
- Fallback screenshots/cards if embed unavailable

Section: Self-host cleanly

- Docker image
- Volumes
- Config/env
- Backups
- Optional Rybbit analytics

Section: Privacy and operator control

- Local files stay under operator/operator-host control.
- Analytics is optional.
- No filesystem mutation without explicit confirmation.

Section: For tables

- Player/GM handoff
- Remote use
- Browser access
- Desktop-like workflow without requiring desktop install.

## Visual direction

Preserve the existing RunSite visual language if it is already strong.

If the current page is placeholder-quality, make it feel deliberate:

- Tactical desktop/browser aesthetic.
- Interactive panels.
- Tour hotspot cards.
- Strong product copy.
- Avoid generic SaaS-purple styling.

## Deliverables

- Updated RunSite page/sections for the 3D tour/LTD idea.
- Rybbit enabled/configurable via env.
- Docker/self-host CTA and copy.
- Clear fallback if the 3D tour provider cannot embed.
- Short docs or comments explaining env requirements.
- Do not deploy unless explicitly asked.

