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
  - signed-in home/work aftermath recap visibility on the calmer home cockpit
  - signed-in home/work governed roster-move visibility on the calmer home cockpit
  - route-readiness gating so `/home/access` and `/home/work` unlock once real device/return truth exists even if onboarding was not explicitly marked complete yet
  - safehouse / travel mode visibility, staged offline inventory, and recap follow-through

## What just landed

- Added a dedicated `Aftermath recap` card on `/home/work` with bounded summary, evidence, return-shelf context, and a deep link back to the shared workspace return lane
- Added a dedicated `Roster move` card on `/home/work` so the latest governed transfer stays visible on the signed-in home cockpit and points back to the same operator rail
- Extended the shared campaign summary on signed-in home to call out aftermath-package count alongside GM prep and travel readiness
- Replaced the blunt onboarding-only gate on `/home/access` and `/home/work` with route-readiness checks based on actual device, support, install, and campaign-return truth
- Taught `scripts/hub-live-audit.py` to verify both `/home/access` and the new `/home/work` aftermath lane after it drives prep launch, travel prefetch, aftermath recap packaging, and roster transfer on the live edge
- Extended `scripts/hub-live-audit.py` again so `/home/work` also has to show the latest governed roster move after the signed-in transfer action lands
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

1. Deepen organizer/operator depth on the same account/control backbone without inventing a parallel admin model.
2. Push more of the campaign workspace v3 follow-through into durable receipts and shared projections instead of isolated cards, especially downtime/next-session carry-forward and consequence follow-through.
3. Keep moving toward the cross-repo journey-proof gap: install -> claim -> restore -> continue and join campaign -> run -> recover -> recap still need stronger whole-product acceptance evidence outside this repo.

## Guardrails

- Keep Hub bounded to relationship plane, campaign spine, control/support, public guide/home/downloads, and orchestration adapters.
- Do not duplicate registry publication/install truth, media execution ownership, or engine/runtime semantics inside Hub.
- Prefer governed receipts and shared projections over local shadow models.
