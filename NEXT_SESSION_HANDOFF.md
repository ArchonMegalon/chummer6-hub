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
  - safehouse / travel mode visibility, staged offline inventory, and recap follow-through

## What just landed

- Persisted governed aftermath recap packages in Hub campaign truth
- Added `/api/v1/campaign-spine/me/workspaces/{workspaceId}/aftermath-recap-packages`
- Added the signed-in `Generate aftermath recap package` action on `/account/work/workspaces/{workspaceId}`
- Added aftermath recap packages to workspace detail, work rails, recap shelf projections, creator-publication inputs, and bounded change-packet projections
- Kept the travel-prefetch lane visible before a device is claimed and kept the new aftermath lane tied to the same shared return rail
- Taught `scripts/hub-live-audit.py` to verify prep launch, travel prefetch, aftermath recap packaging, and roster transfer on the live edge after minting a real install claim
- Refreshed local proof artifacts and smoke coverage for the new lane

## Verify first

```bash
dotnet build Chummer.Run.Api/Chummer.Run.Api.csproj -v minimal
dotnet test Chummer.Run.sln -v minimal
bash scripts/ai/run_services_smoke.sh
bash scripts/audit-compliance.sh
docker compose -f docker-compose.public-edge.yml up -d --build
python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work
CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh
```

## Next highest-impact gaps

1. Deepen organizer/operator depth on the same account/control backbone without inventing a parallel admin model.
2. Push more of the campaign workspace v3 follow-through into durable receipts and shared projections instead of isolated cards, especially downtime/next-session carry-forward and consequence follow-through.
3. Keep moving toward the cross-repo journey-proof gap: install -> claim -> restore -> continue and join campaign -> run -> recover -> recap still need stronger whole-product acceptance evidence outside this repo.

## Guardrails

- Keep Hub bounded to relationship plane, campaign spine, control/support, public guide/home/downloads, and orchestration adapters.
- Do not duplicate registry publication/install truth, media execution ownership, or engine/runtime semantics inside Hub.
- Prefer governed receipts and shared projections over local shadow models.
