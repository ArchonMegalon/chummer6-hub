# ADR-0017: world-state and mission-market layer above the campaign spine

## Status

Proposed

## Context

Project Chummer already has:
- deterministic engine truth
- campaign and living-dossier spine
- campaign workspace and device-role model
- rule-environment and amend truth
- publication and artifact lanes
- product-control and support closure plane

The next major widening idea is a persistent world-state and mission-market layer where factions, districts, projects, and strategic pressure generate opportunities and consequences across campaigns.

If this layer is pursued, it needs a clean home and future-proof boundaries now.

## Decision

Project Chummer will treat the world-state and mission-market layer as:

1. a **future-capability horizon** first (`BLACK LEDGER`),
2. a future **shared contract family** (`Chummer.World.Contracts`) distinct from `Chummer.Campaign.Contracts` and `Chummer.Control.Contracts`,
3. a layer that **feeds campaigns** rather than replacing campaigns,
4. a layer where GM or organizer approval remains required for canonical world-impacting outcomes.

## Consequences

### Positive

- preserves a clean campaign contract family
- gives future organizer and manager-player modes a real semantic home
- allows world-linked jobs and consequences without corrupting campaign or rules truth
- creates a path toward city-state, season operations, and artifact-rich mission markets

### Negative

- adds another future contract family to maintain
- increases future Hub bounded-context complexity
- requires explicit authority modeling for organizer, GM, and later faction-seat roles

## Non-negotiable boundaries

- world-state must not silently mutate rules truth
- world-state must not derive canonical truth from passive surveillance or debrief tooling
- world-state must not force every table into a shared metagame
- world-state must not collapse into the support/control plane

## Follow-up

If the horizon remains active, design should add:
- `products/chummer/horizons/black-ledger.md`
- `WORLD_STATE_AND_MISSION_MARKET_MODEL.md`
- `BLACK_LEDGER_FOUNDATION_CHANGE_GUIDE.md`

Later build work should start with a **GM-only world engine** before any human faction seats are introduced.
