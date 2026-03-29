# Next Session Handoff

Updated: 2026-03-29

## Current state

- Local docker public edge is the active proof lane for `chummer.run`
- Public and signed-in live audits are green on the rebuilt edge
- Wave 1 campaign workspace work now includes:
  - governed roster transfer operator flow
  - governed prep-library search
  - governed prep launch receipts on the shared workspace
  - governed travel-prefetch receipts on the shared workspace
  - governed aftermath recap packages on the shared workspace
  - governed next-session carry-forward packets on the shared workspace and server plane
  - governed downtime brief packets on the shared workspace and server plane
  - richer operator operations pulse and campaign-return pulse on the shared account/control backbone
  - explicit season/event operator rail on the shared account/control backbone
  - signed-in home/work aftermath recap visibility on the calmer home cockpit
  - signed-in home/work downtime brief visibility on the calmer home cockpit
  - signed-in home/work next-session carry-forward visibility on the calmer home cockpit
  - signed-in home/work governed consequence follow-through visibility on the calmer home cockpit
  - signed-in home/work governed roster-move visibility on the calmer home cockpit
  - signed-in home/work latest prep-launch and travel-prefetch receipt visibility on the calmer home cockpit
  - signed-in home/work operator-posture visibility on the calmer home cockpit
  - route-readiness gating so `/home/access` and `/home/work` unlock once real device/return truth exists even if onboarding was not explicitly marked complete yet
  - safehouse / travel mode visibility, staged offline inventory, and recap follow-through

## What just landed

- Added a dedicated `Aftermath recap` card on `/home/work` with bounded summary, evidence, return-shelf context, and a deep link back to the shared workspace return lane
- Added a dedicated `Downtime brief` card on `/home/work` and matching `/account/work/workspaces/{workspaceId}` detail so downtime obligations and next-session follow-through stop hiding inside the generic aftermath list
- Added a first-class `Next-session carry-forward` projection to the shared workspace and server plane, then surfaced it on both `/account/work/workspaces/{workspaceId}` and `/home/work` with return-lane truth, next-step truth, and bounded evidence
- Deepened `Teams & permissions` with an explicit operator `Operations pulse`, campaign-return pulse, and bounded watchouts instead of leaving organizer posture at raw counts and one roster-move drawer
- Added a first-class `Season / event pulse` and `Season & event rail` to `Teams & permissions`, backed by governed run, carry-forward, change-packet, and recap receipts from the shared campaign/operator projection
- Extended the signed-in `/home/work` operator card so it now carries the operator operations pulse, campaign-return pulse, and a bounded watchout from the same shared projection
- Extended the signed-in `/home/work` operator card so it now also carries the operator season/event pulse and one bounded recent-event receipt from the same shared projection
- Deep-linked the signed-in `/home/work` operator card directly into the exact `Season & event rail` drawer on `/account/work` instead of dropping users at the generic operator shell
- Added a dedicated `Consequence watch` card on `/home/work` so the lead governed campaign consequence and one evidence cue stay visible on the signed-in home cockpit instead of only appearing inside the shared summary prose
- Added a dedicated `Roster move` card on `/home/work` so the latest governed transfer stays visible on the signed-in home cockpit and points back to the same operator rail
- Extended the `/home/work` GM prep card so it now carries the latest governed prep-launch packet title and the latest staged travel-prefetch device receipt instead of only generic posture text
- Added a dedicated `Operator posture` card on `/home/work` so the lead governed operator group, its visibility posture, roster state, and latest audit cue stay visible on the same signed-in route
- Extended the shared campaign summary on signed-in home to call out aftermath-package count alongside GM prep and travel readiness
- Replaced the blunt onboarding-only gate on `/home/access` and `/home/work` with route-readiness checks based on actual device, support, install, and campaign-return truth
- Taught `scripts/hub-live-audit.py` to verify both `/home/access` and the new `/home/work` aftermath lane after it drives prep launch, travel prefetch, aftermath recap packaging, and roster transfer on the live edge
- Extended `scripts/hub-live-audit.py` again so `/home/work` also has to show the latest governed roster move after the signed-in transfer action lands
- Extended `scripts/hub-live-audit.py` again so `/home/work` also has to show the operator-posture card and its route back to `Teams & permissions`
- Extended `scripts/hub-live-audit.py` again so `/home/work` also has to show the dedicated consequence card after the signed-in workspace journey resolves
- Extended `scripts/hub-live-audit.py` again so both `/home/work` and `/account/work/workspaces/{workspaceId}` have to show the next-session carry-forward surface on the live edge
- Extended `scripts/hub-live-audit.py` again so the live signed-in journey now generates and verifies both a session recap package and a downtime brief package on the rebuilt edge
- Extended `scripts/hub-live-audit.py` again so `/account/work` has to show the richer organizer `Operations pulse` on the rebuilt edge
- Extended `scripts/hub-live-audit.py` again so both `/account/work` and `/home/work` have to show the new organizer season/event rail on the rebuilt edge
- Extended smoke coverage so source assertions lock the new home card and route-readiness gate in place
- Verified the rebuilt local `chummer.run` edge with both host-level live audit and Playwright e2e against the already-running docker edge

## Verify first

```bash
dotnet build Chummer.Run.Api/Chummer.Run.Api.csproj -v minimal
dotnet test Chummer.Run.sln -v minimal
bash scripts/ai/run_services_smoke.sh
bash scripts/audit-compliance.sh
docker compose -f docker-compose.public-edge.yml up -d --build
python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work
CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh
CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh
```

## Next highest-impact gaps

1. Keep deepening organizer/operator depth on the same account/control backbone without inventing a parallel admin model, especially beyond the new season/event rail into broader community, league, and multi-event operations.
2. Push more of the campaign workspace v3 follow-through into durable receipts and shared projections instead of isolated cards, especially shared consequence/recap synthesis and broader long-lived campaign memory beyond the new next-session and downtime packets.
3. Keep moving toward the cross-repo journey-proof gap: install -> claim -> restore -> continue and join campaign -> run -> recover -> recap still need stronger whole-product acceptance evidence outside this repo.

## Guardrails

- Keep Hub bounded to relationship plane, campaign spine, control/support, public guide/home/downloads, and orchestration adapters.
- Do not duplicate registry publication/install truth, media execution ownership, or engine/runtime semantics inside Hub.
- Prefer governed receipts and shared projections over local shadow models.
