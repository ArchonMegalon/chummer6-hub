# Black Ledger Map Tech Stack Decision

## Current shipped decision

Current public shipping posture:

- ASP.NET Razor integration
- first-party canvas geoscape renderer
- API-backed faction/event/arc/replay data binding
- bounded SVG tactical shell retained as fallback only
- reduced-motion and list fallback built into the same surface

## Why

- low dependency risk
- no provider branding
- works inside the current Hub runtime
- keeps globe rendering first-class while preserving a bounded fallback

## Upgrade path

If the geoscape needs heavier rendering later, upgrade behind the same contracts:

- Three.js
- deck.gl
- PixiJS
- GSAP
- custom WebGL layers

Those dependencies may render. They must not own truth.
