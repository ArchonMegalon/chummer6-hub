# Next Session Handoff

Updated: 2026-03-30T07:18:59+02:00

## Handoff refresh (2026-03-30T07:18:59+02:00)

- The public-edge compose lane now mounts Fleet’s published artifact canon directly into the live portal container at `/fleet-artifacts` and sets `CHUMMER_PUBLIC_FLEET_ARTIFACT_ROOT=/fleet-artifacts`, so `/api/public/weekly-pulse` on `chummer.run` reflects current Fleet readiness instead of stale baked-in mirror data.
- `tests/RunServicesSmoke/Program.cs` now accepts the governed launch-readiness variants that can legitimately appear once journey proof is ready, rather than hard-coding only the older `route-canary validation` wording.
- Re-verified clean with:
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`
- Live proof after the mount fix: `/api/public/weekly-pulse` now reports `journey proof is ready` on the rebuilt local `chummer.run` edge.

## Handoff refresh (2026-03-30T06:49:05+02:00)

- Commit `e3a34688` (`Refine provider route weekly pulse decisions`) is on `main` and matches `origin/main`.
- `WeeklyProductPulseArtifactService` now derives provider-route `review_due` from generated evidence timestamps instead of only mirroring the seed date, and it makes the provider-route `next_decision` evidence-aware when live proof and support-closure posture are available.
- The mirrored [WEEKLY_PRODUCT_PULSE.generated.json](/docker/chummercomplete/chummer6-hub/.codex-design/product/WEEKLY_PRODUCT_PULSE.generated.json) was refreshed so the design mirror again carries `closure_health`, `adoption_health`, and `progress_trend` blocks alongside provider-route stewardship.
- Added/updated weekly-pulse artifact tests covering the derived provider-route review date and the hold-on-proof-failure decision path.
- Re-verified clean with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "WeeklyProductPulseArtifactServiceTests|PublicTrustPulseServiceTests|VerificationEntryPointTests|DesignMirrorExecutionPlanTests"`
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T06:39:23+02:00)

- Commit `4dacd824` (`test: harden live trust surface verification`) is on `main` and matches `origin/main`.
- `scripts/hub-live-audit.py` now requires the rendered trust-trend rail on `/`, `/downloads`, `/help`, and `/now`, and it also verifies that signed-in `/downloads`, `/now`, and `/help` expose `Recommended for this install`, `Install posture`, and the fix-ready trust state after the linked install is refreshed.
- `scripts/e2e-hub-playwright.cjs` now asserts the same signed-in trust rows and the rendered `.trust-pulse-trend__point` rail on `/downloads`, `/now`, and `/help`, so the browser proof catches missing trust-surface rendering rather than only route availability.
- Re-verified clean on the current local edge with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T06:34:49+02:00)

- Commit `b6366275` (`Visualize trust trends and route verify-ready fixes`) is already on `main` and matches `origin/main`.
- The shared weekly trust pulse panel now renders measured progress points directly from `ProgressTrendSamples` instead of leaving the trend only in prose.
- `PublicTrustPulsePanelViewModel` now carries explicit trend samples, `_PublicTrustPulsePanel.cshtml` renders them, and `site.css` adds the compact trend rail styling used by `/`, `/help`, `/downloads`, and `/now`.
- Verification coverage now asserts the new trend-sample rail is part of the public trust pulse model, and the shared verification entry-point test locks the new panel/view-model seam in place.
- Re-verified clean on the rebuilt local edge with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "PublicTrustPulseServiceTests|VerificationEntryPointTests"`
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`

## Handoff refresh (2026-03-30T06:27:17+02:00)

- Commit `eb2ab8eb` (`Deepen install-specific trust and pulse fallback`) is already on `main` and matches `origin/main`.
- Signed-in downloads trust status now includes install-aware `Recommended for this install` and `Install posture` rows so a linked install can be compared against both the promoted public shelf and any support-directed fix lane.
- `PublicTrustPulseService` now prefers the synthesized weekly-pulse `supporting_signals.adoption_health` and `supporting_signals.progress_trend` blocks when present, while still backfilling raw progress/local-proof metadata when those artifacts exist.
- Trust-pulse fixture coverage is now pinned to temp-local optional artifact paths so test results do not bleed in from repo-local generated canon files.
- Smoke coverage now locks the new signed-in downloads rows in both update-needed and verification-ready states.
- Re-verified clean on the rebuilt local edge with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "WeeklyProductPulseArtifactServiceTests|PublicTrustPulseServiceTests|VerificationEntryPointTests|DesignMirrorExecutionPlanTests"`
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`
 
## Handoff refresh (2026-03-29T21:45:00+02:00)

- Local execution status is clean and green from the required full verification loop:
  - `docker compose -f docker-compose.public-edge.yml up -d --build` completes successfully.
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work` passes.
  - `bash scripts/ai/run_services_smoke.sh` passes.
  - `bash scripts/run_smoke.sh` passes.
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh` passes.
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh` passes.
- Cross-repo build blocker from prior runs was the duplicated-attribute failure in `chummer-core-engine/Chummer.Contracts` during docker rebuild; resolved by pruning generated local artifacts in that adjacent repo before build (`../chummer-core-engine/Chummer.Contracts/obj_tmp` and stale `obj`) and not committing those external repo changes.
- Working tree for this repo is currently clean after cleanup; no untracked artifacts remain.

## Handoff refresh (2026-03-29T22:05:00+02:00)

- Product pulse v2 moved from mostly mirrored-static trust fields to a synthesized evidence path:
  - Added `WeeklyProductPulseArtifactService` to compose `/api/public/weekly-pulse` from the mirrored pulse plus live evidence overlays from:
    - `.codex-design/product/PROGRESS_REPORT.generated.json`
    - `.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json`
    - `/docker/fleet/.codex-studio/published/JOURNEY_GATES.generated.json`
    - `/docker/fleet/.codex-studio/published/SUPPORT_CASE_PACKETS.generated.json`
    - `/docker/fleet/.codex-studio/published/STATUS_PLANE.generated.yaml`
- Public trust surfaces now expose a first-class `Closure health` row backed by the synthesized weekly pulse instead of leaving support follow-through trapped in packet artifacts.
- `PublicTrustPulseService` now reads the synthesized weekly pulse JSON rather than loading the mirrored pulse file directly.
- Mirrored `WEEKLY_PRODUCT_PULSE.generated.json` was refreshed to include the new `closure_health` block and the updated summary language.
- Verification added:
  - new unit tests for `WeeklyProductPulseArtifactService`
  - extended trust-pulse service tests for closure-health derivation
  - entry-point/design-mirror assertions updated for the synthesized pulse path
  - run-services smoke now asserts `Closure health` on landing and current-release trust panels
- Full post-change verification passed:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "WeeklyProductPulseArtifactServiceTests|PublicTrustPulseServiceTests|VerificationEntryPointTests|DesignMirrorExecutionPlanTests"`
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`

## Handoff refresh (2026-03-29T22:10:00+02:00)

- Extended the synthesized weekly pulse artifact further so `/api/public/weekly-pulse` now includes machine-readable:
  - `supporting_signals.adoption_health`
  - `supporting_signals.progress_trend`
  - alongside the already-added `supporting_signals.closure_health`
- Adoption health now derives from the local release proof plus progress-report history depth.
- Progress trend now derives directly from `PROGRESS_HISTORY.generated.json` and publishes direction, delta, range, summary, and bounded sample points.
- The mirrored `WEEKLY_PRODUCT_PULSE.generated.json` was refreshed to include the new adoption/trend blocks so static canon and synthesized runtime stay aligned.
- Smoke coverage now asserts that `/api/public/weekly-pulse` exposes closure-health, adoption-health, and measured progress-trend samples.
- Full post-change verification passed again:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "WeeklyProductPulseArtifactServiceTests|PublicTrustPulseServiceTests|VerificationEntryPointTests|DesignMirrorExecutionPlanTests"`
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`

## Current state (2026-03-29T21:33:00+02:00)

- Implemented trust-pulse trend surfacing from `PROGRESS_HISTORY.generated.json` into public trust rows.
- Added a new `Progress trend` row on `/now`, `/downloads`, and `/help` trust pulse panel through `PublicLandingController`.
- Extended `PublicTrustPulseService` and snapshot model with trend direction/delta and history source metadata.
- Added service tests for history loading and trend calculation, plus verification test coverage for the new `Progress trend` row.
- Hardened `scripts/hub-live-audit.py` fetch path with bounded 429 retry/backoff and expanded trust-row required snippets to include `Progress trend`.
- Re-ran full verification sequence: build/tests, `run_smoke.sh`, live audit, non-playwright e2e, and Playwright e2e (all passing after local rate-limit retries).

Remaining immediate gap
- Long-form trend chart/sparkline visuals are still absent from trust panels; currently shows summary delta only.
- Follow-up could include multi-point trend bullets in panel micro-proof if desired.

## Current state

- Local docker public edge is the active proof lane for `chummer.run`
- Public and signed-in live audits are green on a clean `docker compose -f docker-compose.public-edge.yml up -d --build` cycle
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
  - explicit sponsor-session operator rail on the shared account/control backbone
  - explicit league/season operations rail on the shared account/control backbone
  - support assistant verification-ready action on install-current reporter cases
  - live-edge proof for the signed-in support assistant verification loop on a claimed install
  - multi-campaign preview season bootstrap on one operator group
  - signed-in home/work aftermath recap visibility on the calmer home cockpit
  - signed-in home/work downtime brief visibility on the calmer home cockpit
  - signed-in home/work next-session carry-forward visibility on the calmer home cockpit
  - signed-in home/work governed consequence follow-through visibility on the calmer home cockpit
  - signed-in home/work governed roster-move visibility on the calmer home cockpit
  - signed-in home/work latest prep-launch and travel-prefetch receipt visibility on the calmer home cockpit
  - signed-in home/work operator-posture visibility on the calmer home cockpit
  - route-readiness gating so `/home/access` and `/home/work` unlock once real device/return truth exists even if onboarding was not explicitly marked complete yet
  - safehouse / travel mode visibility, staged offline inventory, and recap follow-through
  - signed-in and public trust pulse now exposes install-aware `Who can get it now` and `Adoption health`
  - signed-in and public trust pulse now also exposes `Launch readiness` plus `Provider-route stewardship` from the weekly pulse instead of leaving those milestone-20 signals trapped in canon JSON
  - campaign memory projection now appears on signed-in home/work and workspace detail where available
  - home starter lane now nudges linked users without existing campaign work into `/home/work` as a first-playable-session onboarding step
  - `/account/work` empty state now offers the same `Start first playable session` starter action instead of a dead-end generic message
  - shared workspace, workspace digest, and workspace server-plane projections now carry a bounded `First playable session` proof while the campaign is still in its kickoff state
- signed-in `/home/work` and `/account/work/workspaces/{workspaceId}` now surface first-session campaign-start proof, bounded evidence, and a direct route back into the same shared workspace detail
- /auth/email/start now reliably returns a preview callback link on local edge, allowing signed-in workflow assertions to execute full callback/restore verification.

## What just landed

- Added a first-class `First playable session` projection to the shared workspace, calmer workspace digest, and bounded workspace server plane so starter-lane onboarding becomes real campaign-start proof instead of only a seeding button
- Surfaced that first-session proof on both `/home/work` and `/account/work/workspaces/{workspaceId}` with campaign-start summary, bounded evidence, and the same next-step truth already used by the shared workspace
- Retired the first-session proof automatically once governed prep launch, travel prefetch, or recap follow-through lands, so the starter lane does not linger after the campaign moves into durable continuity
- Extended `PublicTrustPulseService` and signed-in/public trust-pulse rows so landing, downloads, help, and current-release surfaces now carry `Launch readiness` plus `Provider-route stewardship` straight from the weekly pulse
- Added unit and smoke assertions that lock those launch/provider pulse rows into the public and signed-in surfaces instead of leaving them as unguarded controller copy
- Refreshed the local mirrored weekly pulse artifact with launch/provider fields and made stack smoke tolerate alternate compose entry files, missing `haproxy.cfg`, and healthy `307` redirect posture on the public edge
- Added a `Start first playable session` action on `/account/work` empty-state copy so signed-in work follows the same starter-lane onboarding route as `/home/work`
- Reused `/api/v1/campaign-spine/me/workspaces/starter` from the account route and added starter-lane feedback/redirect handling instead of inventing a second onboarding API
- Added a dedicated `Aftermath recap` card on `/home/work` with bounded summary, evidence, return-shelf context, and a deep link back to the shared workspace return lane
- Added a dedicated `Downtime brief` card on `/home/work` and matching `/account/work/workspaces/{workspaceId}` detail so downtime obligations and next-session follow-through stop hiding inside the generic aftermath list
- Added a first-class `Next-session carry-forward` projection to the shared workspace and server plane, then surfaced it on both `/account/work/workspaces/{workspaceId}` and `/home/work` with return-lane truth, next-step truth, and bounded evidence
- Deepened `Teams & permissions` with an explicit operator `Operations pulse`, campaign-return pulse, and bounded watchouts instead of leaving organizer posture at raw counts and one roster-move drawer
- Added a first-class `Season / event pulse` and `Season & event rail` to `Teams & permissions`, backed by governed run, carry-forward, change-packet, and recap receipts from the shared campaign/operator projection
- Extended the signed-in `/home/work` operator card so it now carries the operator operations pulse, campaign-return pulse, and a bounded watchout from the same shared projection
- Extended the signed-in `/home/work` operator card so it now also carries the operator season/event pulse and one bounded recent-event receipt from the same shared projection
- Deep-linked the signed-in `/home/work` operator card directly into the exact `Season & event rail` drawer on `/account/work` instead of dropping users at the generic operator shell
- Fixed the campaign spine so one operator group can safely carry more than one governed campaign by resolving crew ids per campaign, keeping campaign-bound dossiers scoped by owner plus campaign instead of collapsing back to one member dossier, and narrowing roster-transfer overwrite checks to the selected target campaign
- Seeded a second governed `preview season` campaign on the default personal operator group and extended smoke coverage so organizer summaries now prove a real multi-campaign season rail instead of a single-campaign placeholder
- Added a first-class multi-campaign `Season board` to `Teams & permissions`, backed by governed workspace projections so each campaign lane shows its lead run, latest event receipt, next safe action, watchout, and direct shared-workspace route
- Added a first-class `League / season operations` rail to `Teams & permissions`, backed by governed league summaries and bounded audit lines so multi-campaign organizer work stops living across disconnected drawers
- Extended the signed-in `/home/work` operator card so it now shows one lead `Season board` lane and deep-links directly into the exact board drawer on `/account/work`
- Extended the signed-in `/home/work` operator card so it now also carries a bounded league-and-season operations summary and a direct route into the new league rail on `/account/work`
- Extended the signed-in live audit so `/account/work` now has to render the season-board entries and their direct shared-workspace routes on the rebuilt edge
- Extended the signed-in live audit so `/account/work` and `/home/work` also have to render the new league-and-season operations rail after the signed-in transfer flow resolves
- Extended public trust pulses on `/now`, `/downloads`, and `/help` so both anonymous and signed-in paths expose install-aware `Who can get it now` and `Adoption health` evidence from proof artifacts
- Exposed campaign memory in signed-in `/home/work`, `/account/work/workspaces/{workspaceId}`, and `/account/work` home surfaces so recall and transition state remains visible across campaign memory boundaries
- Tightened the grounded support assistant so reporter-facing fix questions now escalate from “read the timeline” to an explicit `Verify fix now` action once the linked install is already on the reporter-ready build
- Extended smoke coverage so verification-ready assistant answers must explicitly point back to the tracked case detail and tell the reporter to use the live verification buttons
- Extended `scripts/hub-live-audit.py` so the rebuilt local `chummer.run` edge now submits a real signed-in support case, moves it through internal release and reporter notification, refreshes the claimed install onto the fix build, asks the assistant before and after the update, and proves the `Verify fix now` action plus reporter confirmation on `/account/support/{caseId}`
- Extended `scripts/cleanup_synthetic_support_cases.py` so synthetic support cases created by the live signed-in audit are cleaned up if a later run exits before reporter confirmation
- Fixed bounded receipt retention for governed prep launches, travel-prefetch receipts, and aftermath recap packages so the newest receipts survive once the local proof store crosses its 64-item cap
- Biased signed-in home lead-workspace ordering toward the richer live lane when two workspaces share the same latest transfer timestamp, so `/home/work` keeps the active prep/aftermath lane instead of drifting to a thinner transfer-only lane
- Extended smoke coverage with an aftermath-retention overflow regression so the newest generated recap package must remain visible on `/home/work` after the cap is exceeded
- Added a first-class `Member guidance rail` to `Teams & permissions` so organizers can point people to the real current-release, download, help/trust, and support-closure surfaces from the same operator backbone
- Extended the signed-in `/home/work` operator card so it now carries bounded organizer guidance copy plus a direct route to the member-guidance rail on `/account/work`
- Extended the signed-in live audit so both `/account/work` and `/home/work` have to surface the new organizer guidance rail on the rebuilt edge
- Added a first-class `Invite & sponsorship rail` to `Teams & permissions` so operators can issue governed join codes and boost codes without leaving the shared account/control backbone
- Added a first-class `Recent sponsor sessions` rail to `Teams & permissions`, backed by governed sponsor-session projections so operators can see who is attached, which campaign lane they are on, and the current sponsorship status without leaving the same operator surface
- Added explicit stale-code recovery copy and problem-detail recovery guidance so missing or expired join/boost codes now point users back to a fresh governed code and the same member-guidance rail instead of leaking repo vocabulary
- Backfilled the default preview operator group with governed invite and sponsorship capabilities so the signed-in organizer rail is materially usable on the rebuilt local edge, not just on manually created campaign groups
- Extended the signed-in `/home/work` operator card so it now carries one bounded sponsor-session pulse and deep-links directly into the sponsor-session rail on `/account/work`
- Extended the signed-in live audit so it now creates and consents a real governed sponsor session, re-reads the shared campaign spine, and proves the sponsor-session rail on both `/account/work` and `/home/work`
- Extended the signed-in live audit so it now issues real join and boost codes, verifies the stale-code recovery responses, and proves the new invite rail on both `/account/work` and `/home/work`
- Reordered community operator projections so the signed-in `/home/work` operator card prefers the freshest and richest governed operator lane instead of falling back to alphabetical group order
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
- Added a local proof fix for intermittent portal<->identity network regressions by validating service attachment during compose verification and validating email-start flow through fallback local identity path.
- Added starter-lane onboarding to signed-in public home and campaign spine:
  - `/home/work` now unlocks with `effectiveWorkSurfaceReady` for seedable starter install states.
  - `/api/v1/campaign-spine/me/workspaces/starter` now provides the starter workspace payload used by the onboarding button.
  - `/home/work` starter path now deep-links to `/account/work/workspaces/{workspaceId}` and falls back cleanly when starter seeding is not yet available.
- Extended signed-in home and account work build-path cards with planner-coverage summary plus evidence lines:
  - `PlannerCoverageSummary` and `PlannerCoverageLines` now flow into projection DTOs, UI cards, and support-assistant citations.
- Extended smoke/API assertions to validate the starter endpoint and coverage payload, and updated local proof marker generation inputs.
- Completed milestone 19 in `.codex-design/product/NEXT_20_BIG_WINS_AFTER_POST_AUDIT_CLOSEOUT_REGISTRY.yaml`.
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

## Recent verification outcome

- Host-level smoke, compliance, and non-Playwright e2e checks pass on current docker edge.
- Signed-in Playwright/live-audit checks pass end-to-end on current docker edge for the account/work journey (including email callback flow, signed workspace, support flow, and operator rails).

## Next highest-impact gaps

1. Keep deepening organizer/operator depth on the same account/control backbone without inventing a parallel admin model, especially beyond the new season/event rail into broader community, league, and multi-event operations.
2. Push more of the campaign workspace v3 follow-through into durable receipts and shared projections instead of isolated cards, especially shared consequence/recap synthesis and broader long-lived campaign memory beyond the new next-session and downtime packets.
3. Keep moving toward the cross-repo journey-proof gap: install -> claim -> restore -> continue and join campaign -> run -> recover -> recap still need stronger whole-product acceptance evidence outside this repo.
4. Continue the guided onboarding slice past first-session proof into broader first-session closure and first return, especially once the kickoff lane needs stronger support, recap, and community/operator follow-through without reopening a parallel onboarding model.
5. Keep pushing milestone-20 pulse depth behind the new surface rows: real trend history, measured closure/adoption deltas, and provider-route canary automation still need to flow from evidence generation into the weekly pulse without hand-tended prose.

## Latest session snapshot

- Ran `docker compose -f docker-compose.public-edge.yml down && docker compose -f docker-compose.public-edge.yml up -d --build` and re-validated:
  - `python3 scripts/hub-live-audit.py --verify-http-redirects`
  - `python3 scripts/hub-live-audit.py --verify-signed-in-work`
  - `bash scripts/run_smoke.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
- Observed both containers correctly attached to `chummer5a_default` and `codex-fleet-net`; `/auth/email/start` now returns `/auth/email/callback` in the rendered preview and callback workflow completes.
- No source-code functionality changes were required in this session; the remaining work is remaining design-maturity and wave completion evidence.

## Guardrails

- Keep Hub bounded to relationship plane, campaign spine, control/support, public guide/home/downloads, and orchestration adapters.
- Do not duplicate registry publication/install truth, media execution ownership, or engine/runtime semantics inside Hub.
- Prefer governed receipts and shared projections over local shadow models.
