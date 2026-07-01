# Premium UI Design Exit Gate

This gate decides whether Chummer public UI is premium enough to ship, not whether it merely has valid markup or a dark theme. Passing means the product looks intentional before a user reads the fine print.

## Source Standards

Use famous design systems as calibration, not as visual skins to copy:

- Apple Human Interface Guidelines: clarity, deference, depth, direct manipulation, and touch-safe controls.
- Material Design 3: deliberate color roles, typography, motion, layout, and component affordance.
- Microsoft Fluent 2: coherent tokens, elevation, spacing, focus, and cross-platform behavior.
- IBM Carbon Design System: 2x grid discipline, accessible structure, purposeful density, and production consistency.
- Atlassian Design System: clear product language, predictable navigation, and humane workflow density.
- Shopify Polaris: task-first action hierarchy, useful empty states, and commerce-grade decision clarity.
- GOV.UK Service Manual: plain-language service journeys where the next step is never ambiguous.
- WCAG 2.2: contrast, visible focus, input readability, keyboard use, and touch target discipline.
- Nielsen Norman Group usability heuristics: status visibility, recognition over recall, consistency, feedback, and recovery.
- These famous systems are calibration, not skins; Chummer keeps its own campaign-command identity.

## Exit Bar

The UI fails if it looks like a generic dashboard, a proof harness, a provider adapter, a roadmap control plane, or a thin wrapper around internal state. It passes only when it projects one coherent Chummer identity: serious Shadowrun character management, faster table play, durable session continuity, and honest install/support paths.

The five-second verdict must be clear: a new visitor knows this is Chummer, understands it is a Shadowrun character manager, sees the current download path, sees Build and Play as separate Chummer entry points, and can find help without scanning the page.

The one-route-one-job rule applies to every critical public route. The landing page explains and routes. Downloads gets the user onto the right build. Status tells users whether to install, wait, or ask for help. Participate shows the hosted board without wrapper noise. Mobile/PWA exposes playtime tracking, install state, ledger opt-in, heat, continuity, and help.

## Premium Visual Scorecard

The premium visual scorecard blocks release unless all items are true:

- Typography has a distinct editorial display stack and readable body stack; default-only stacks are not enough.
- Color uses named semantic roles for canvas, panels, borders, primary text, muted text, primary accent, and danger.
- Elevation has at least two deliberate depth tiers; flat cards everywhere do not pass.
- Layout has a real spatial system with spacing tokens, radius tiers, max-width discipline, and route-specific composition.
- Motion is restrained, purposeful, and guarded by reduced-motion handling.
- Component anatomy is complete: primary, secondary, and ghost actions; header chrome; Open Chummer dropdown; hero; downloads cards; status pill; mobile facts; and participate iframe.
- Dark-mode form controls are fully readable: textboxes, selects, textareas, placeholders, selected options, caret, accent, disabled, hover, and focus states.
- Responsive behavior is designed, not incidental: mobile breakpoints, fluid type/spacing, minmax grids, svh handling, and touch-safe actions are required.
- Touch targets use a 44px action floor on public primary actions, dropdown summaries, and menu rows; compact desktop styling cannot shrink the actual hit area below the mobile play bar.
- Route visual anatomy is inspected on the shared selectors themselves: hero panels, secondary route heroes, download cards, status panels, mobile facts, and iframe containers must carry deliberate background, depth, radius, spacing, and containment decisions.
- Visual evidence receipt coverage is required. Home needs mobile, tablet, laptop, desktop, and wide desktop screenshot QA with the hero and primary CTA visible. Downloads, Status, Ledger map, Help, and Contact need mobile and desktop screenshot QA.
- State and recovery language is part of the visual finish. Loading, empty, unavailable, and fallback states must explain what is happening and give the next useful action.
- Actionable public links must point to product pages, not raw JSON/API endpoints. Background `fetch()` calls can use data routes; user-clickable links, forms, and JS action links cannot expose those routes as the next step.

## Surface Contracts

Landing must carry `Download Chummer` as the primary action and `Open Chummer` as an accessible dropdown with `Build` and `Play` buttons. It must include a polished visual preview, current-platform note, account/help links, and example runners without exposing implementation language.

Downloads must present Stable and Nightly as the first decision, keep other platforms below that decision, show help when setup blocks a table, and keep account linking optional.

Status must show the current install/readiness state, the current caution, and a simple next action split: Downloads or Help.

Participate must be a real iframe surface when the board is available, with lazy loading, same-origin referrer policy, and a small product-language fallback when the board is unavailable.

Mobile/PWA must follow the mobile playtime standard: compact install state, Black Ledger status, opt-in boundary, heat meter, follow action, continuity summary, ledger map route, role entry points, and help. It must not feel like a shrunken desktop dashboard.

## Language Rule

The zero-internal-language rule is release blocking. Public UI must not show proof-dashboard language, receipt phrasing, operator/fleet/governor language, provider names, raw enum names, or internal process labels. Public copy must explain what the user can do next.

## Failure Modes

Fail the gate when:

- The UI can pass by having many gradients, shadows, hover states, or media queries but no route-specific job clarity.
- The UI can pass by stuffing CSS tokens while the actual route surfaces stay flat, transparent, cramped, or below the 44px action floor.
- The UI can pass by satisfying source heuristics while screenshot QA is missing, stale, overflowing, or not covering the routes users actually touch.
- The landing page loses Build or Play.
- Mobile/PWA loses ledger, heat, opt-in, continuity, install, or help affordances.
- Mobile/PWA exposes raw endpoint paths, JSON URLs, route labels, raw enum states, or data plumbing as visible product copy.
- Mobile/PWA turns a JSON/API route into a clickable user action instead of routing to a product page.
- Participate stops being a real iframe surface.
- Form controls become unreadable in dark mode.
- Navigation, buttons, cards, or focus states are styled on one route but absent on sibling routes.
- Public copy reads like implementation status instead of product language.

## Executable Gate

Run:

```bash
python3 scripts/verify_premium_ui_design_exit_gate.py
```

The generated receipt is `.codex-studio/published/PREMIUM_UI_DESIGN_EXIT_GATE.generated.json` with the human report at `.codex-studio/published/PREMIUM_UI_DESIGN_EXIT_GATE.md`.

Canonical marker terms used by the executable gate: 44px action floor, route visual anatomy, public endpoint language ban.
Additional marker terms used by the executable gate: visual evidence receipt, state and recovery language.
