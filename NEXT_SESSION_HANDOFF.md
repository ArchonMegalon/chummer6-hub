# Next Session Handoff

Updated: 2026-03-29

## Current state

- Local docker public edge is the active proof lane for `chummer.run`
- Public and signed-in live audits are green on the rebuilt edge
- Wave 1 campaign workspace work now includes:
  - governed roster transfer operator flow
  - governed prep-library search
  - governed prep launch receipts on the shared workspace
  - safehouse / travel mode visibility

## What just landed

- Persisted governed prep-launch receipts in Hub campaign truth
- Added `/api/v1/campaign-spine/me/workspaces/{workspaceId}/prep-library/launches`
- Added the signed-in `Launch governed prep packet` action on `/account/work/workspaces/{workspaceId}`
- Added recent governed prep-launch receipts to workspace detail and change-packet rails
- Extended smoke, proof, Playwright, and live-audit coverage for the new lane

## Verify first

```bash
dotnet build Chummer.Run.Api/Chummer.Run.Api.csproj -v minimal
dotnet test Chummer.Run.sln -v minimal
bash scripts/ai/run_services_smoke.sh
bash scripts/audit-compliance.sh
docker compose -f docker-compose.public-edge.yml up -d --build
python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work
```

## Next highest-impact gaps

1. Deepen organizer/operator depth on the same account/control backbone without inventing a parallel admin model.
2. Push more of the campaign workspace v3 follow-through into durable receipts and shared projections instead of isolated cards.
3. Keep moving toward the cross-repo journey-proof gap: install -> claim -> restore -> continue and join campaign -> run -> recover -> recap still need stronger whole-product acceptance evidence outside this repo.

## Guardrails

- Keep Hub bounded to relationship plane, campaign spine, control/support, public guide/home/downloads, and orchestration adapters.
- Do not duplicate registry publication/install truth, media execution ownership, or engine/runtime semantics inside Hub.
- Prefer governed receipts and shared projections over local shadow models.
