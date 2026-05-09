# Mobile PWA product specification

## entry points
owner: chummer6-mobile
entry points: `/mobile` and `/pwa` are public entry surfaces for preview shell and support-aware continuity.
verification: Route-level checks in public manifest and closure gates confirm both entry points render with auth-aware redirects.

## offline/reconnect
owner: chummer6-mobile
offline/reconnect: Service worker and offline queue must preserve state until account restore or reconnect.
verification: Gate `gate-mobile-pwa` includes offline/reconnect assertions from generated mobile proof files.

## auth
owner: chummer6-mobile
auth: Account and session handoff must be route-bound with same redirect/claim semantics as desktop surfaces.
verification: Mobile auth journeys are bounded by `/login` and `/account` proof and must include support-friendly recovery.

## session resume
owner: chummer6-mobile
session resume: Resume journeys across tab or app lifecycle with explicit rehydration receipts.
verification: PWA journeys include resume session proof before user-facing “session restored” copy.

## tap target/accessibility
owner: chummer6-mobile
tap target/accessibility: Preserve minimum target sizes and readable semantics for first run and package surfaces.
verification: `npx playwright` accessibility traces plus generated proof artifacts confirm keyboard and tap target closure.

## verification
owner: chummer6-mobile
verification: Keep pwa work as preview-bounded with explicit blocker summary until all journey proof tokens pass.
