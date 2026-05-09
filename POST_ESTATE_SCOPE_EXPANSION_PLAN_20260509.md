# Post-estate scope expansion plan

Source bundles:
- `/home/tibor/chummer-black-ledger-design-bundle.zip`
- `/home/tibor/chummer-ltd-concierge-bundle.zip`

Current status:
- The current QWEN35 estate gate remains green.
- The local design mirror is now synced to the latest Black Ledger and public concierge bundle content in this repo.
- This file defines the next implementation scope beyond the closed estate plan.

## Workstream 1: Black Ledger foundation

Owner repos:
- `chummer-design`
- `chummer.run-services`
- `chummer-core-engine`
- `chummer-presentation`
- `chummer-play`
- `chummer-media-factory`

Design sync landed here:
- `BLACK_LEDGER_FOUNDATION_CHANGE_GUIDE.md`
- `WORLD_STATE_AND_MISSION_MARKET_MODEL.md`
- `adrs/ADR-0017-world-state-and-mission-market-layer.md`
- `horizons/black-ledger.md`

Implementation order:
1. Reserve `Chummer.World.Contracts` and future world subfamilies in design and contract-set canon.
2. Separate future `JobSeed` and `JobPacket` semantics from campaign-run truth.
3. Reserve world-linked rule-environment seams:
   - `WorldOffer`
   - `ThreatTag`
   - `ScenarioModifier`
   - `CampaignOverlayPackage`
4. Reserve organizer capability vocabulary:
   - `world_operator`
   - `season_operator`
   - `faction_seat`
5. Reserve workspace projection zones for world pressure, world-linked jobs, and consequence summaries.
6. Reserve `ResolutionReport` as the approval-aware bridge from run outcome to later campaign/world consequences.
7. Reserve artifact families for city tickers, district heat snapshots, faction propaganda, mission briefings, and season recap outputs.

Verification:
- contract-set canon explicitly names `Chummer.World.Contracts` as future/not-promoted
- campaign and control docs keep world truth distinct from campaign truth and support/control truth
- rule-environment docs expose world-linked mechanics only through explicit receipts
- no flagship or public release posture is widened by this workstream

## Workstream 2: Public concierge and trust-widget implementation

Owner repos:
- `chummer-design`
- `chummer.run-services`
- `chummer-hub-registry`
- `chummer-media-factory`
- `executive-assistant`

Design sync landed here:
- `PUBLIC_CONCIERGE_AND_TRUST_WIDGET_MODEL.md`
- `EXTERNAL_TOOLS_BLOCKING_POLICY_REWORK.md`
- `PUBLIC_CONCIERGE_WORKFLOWS.yaml`
- `LTD_STACK_WOW_FACTOR_CHANGE_GUIDE.md`

Implementation order:
1. Update external-tool inventory and capability map to promote `Lunacal` and `Deftform`, and bound `FacePop` as a Class C1 public-trust widget lane.
2. Implement Hub-owned public concierge wrapper routes for:
   - `/downloads`
   - `/now`
   - creator/consult surfaces
   - invite/join primer surfaces
   - testimonial capture surfaces
3. Add route-level kill switches, CSP/embed policy, locale fallback, and first-party fallback links.
4. Mirror every meaningful branch result into Hub-owned receipts and telemetry with correlation ids.
5. Add webhook receipt ingestion for FacePop, Lunacal, and Deftform without letting any vendor become canonical support, install, account, campaign, or publication truth.
6. Add registry references for reusable concierge assets and approved testimonial/public-proof artifacts.
7. Add moderated testimonial publication flow and media-sibling support in Media Factory.

Verification:
- no widget appears on authenticated, truth-bearing, or runtime-critical surfaces
- first-party fallback still works when any vendor widget is disabled
- telemetry and receipt chains exist for route choice, intake, booking, and approved testimonial outcomes
- public copy remains provider-neutral unless explicitly design-internal
- support truth, install truth, and account truth remain first-party Hub state

## Recommended execution sequence

1. Finish design-canon reservation updates for Black Ledger and concierge policy in the owning design repo.
2. Implement Hub public concierge wrappers and receipt ingestion first because that path produces direct user-facing value without widening flagship claim posture.
3. Land registry and media-factory support for concierge assets and approved testimonials.
4. Only then open the first bounded Black Ledger research slice:
   - GM-only world engine
   - no human faction seats
   - no global player-managed metagame

## Release posture

- Concierge work can ship as bounded public-surface functionality once fallback, receipt, and forbidden-surface rules are proven.
- Black Ledger remains a horizon and architecture-foundation lane until executable mission-market and world-pressure proof exists.
