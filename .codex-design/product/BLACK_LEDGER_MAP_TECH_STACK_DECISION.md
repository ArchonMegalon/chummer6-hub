# Black Ledger Map Tech Stack Decision

## Current shipped decision

Phase 1 ships as:

- ASP.NET Razor view
- first-party canvas geoscape globe
- requestAnimationFrame motion state machine
- first-party SVG tactical shell as fallback only
- route-backed onboarding and faction promo integration

## Why

- low dependency risk
- no provider branding
- works inside the current Hub runtime
- public-safe fallback is first-class instead of an afterthought
- the primary object is now a large globe instead of a flat shell

## Upgrade path

If the command map needs heavier rendering later, upgrade behind the same contracts:

- Three.js
- deck.gl
- CesiumJS
- GSAP

Those dependencies may render. They must not own truth.
