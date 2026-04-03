# Next Session Handoff

Updated: 2026-03-30T11:00:07+02:00

## Handoff refresh (2026-04-03T00:00:00Z)

- Event-control carry-forward now fail-closes relationship-only return cues unless explicit GM ops context is present:
  - `Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs` now requires event/opposition context before relationship split-token carry-forward cues can activate `event_control_packet`.
  - relationship-only carry-forward cues remain governed on `campaign_return_packet` instead of leaking into GM event controls.
- Added focused regression coverage in `Chummer.Tests/CampaignWorkspaceServerPlaneServiceTests.cs`:
  - `EventControlPacketDoesNotActivateFromCarryForwardRelationshipSignalsWithoutEventContext`
  - asserts `event_control_packet` is absent while `campaign_return_packet` remains present under relationship-only carry-forward inputs.
- Re-verified clean with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "FullyQualifiedName~EventControlPacketDoesNotActivateFromCarryForwardRelationshipSignalsWithoutEventContext" --nologo -v minimal`
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "FullyQualifiedName~CampaignWorkspaceServerPlaneServiceTests" --nologo -v minimal`

## Handoff refresh (2026-04-03T00:00:00Z)

- Campaign prep-library synthesis now treats roster movement and aftermath/downtime as first-class governed prep lanes:
  - `Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs` now emits a reusable `roster_movement_packet` from governed `RosterTransfers` and a reusable `aftermath_packet` from governed `AftermathPackages`, then includes both in `BuildPrepPackets(...)`.
  - packet search posture now explicitly covers roster/campaign/crew movement terms and aftermath/downtime/run/artifact continuity terms instead of relying on incidental text from scene/opposition packets.
- Added focused regression coverage in `Chummer.Tests/CampaignWorkspaceServerPlaneServiceTests.cs`:
  - `PrepLibraryIncludesRosterMovementPacketWhenRosterTransfersExist`
  - `PrepLibraryIncludesAftermathPacketWhenAftermathPackagesExist`
- Re-verified clean with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "FullyQualifiedName~CampaignWorkspaceServerPlaneServiceTests" --nologo`

## Handoff refresh (2026-04-02T17:40:42+02:00)

- Public release-truth and desktop platform honesty were tightened around the real shelf instead of internal artifact existence:
  - `Chummer.Run.Api/Services/ReleaseSelectionService.cs` now builds an explicit platform-availability matrix, marks the requested device platform as unavailable when it is off-shelf, and blocks macOS from public visibility until canonical release proof explicitly names the promoted mac artifact route.
  - `Chummer.Run.Api/ViewModels/SiteViewModels.cs`, `Views/PublicLanding/Downloads.cshtml`, and `Views/PublicLanding/Status.cshtml` now expose that matrix to users so `/downloads` and `/status` say which desktop platforms are actually public right now instead of quietly falling through to another platform.
  - `Chummer.Run.Api/Services/HubPageChromeService.cs` now keeps the landing-page header CTA aligned with the landing canon, while `Controllers/PublicLandingController.cs` and `Services/SignedInTrustStatusService.cs` now phrase guest-readable shelves and signed-in follow-through consistently (`Guest-readable handoff` plus `Signed-in handoff` continuity).
- The customer-facing proof rails were repaired rather than weakened:
  - `tests/RunServicesSmoke/Program.cs` now supplies the current `PublicLandingController` constructor dependencies (`ReleaseUploadTicketService`, `IWebHostEnvironment`) and locks the guest-readable shelf expectations plus the off-shelf macOS behavior.
  - `Chummer.Tests/ReleaseSelectionServiceTests.cs` now proves unsupported requested platforms stay unavailable without pretending another platform is recommended, and it proves macOS stays withheld until explicit promoted-proof routes exist.
- Re-verified clean with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "FullyQualifiedName~ReleaseSelectionServiceTests|FullyQualifiedName~PublicReleaseManifestServiceTests" --nologo`
  - `bash scripts/ai/run_services_smoke.sh`
  - `python3 ../chummer-hub-registry/scripts/verify_public_release_channel.py /docker/chummer5a/Docker/Downloads`

## Handoff refresh (2026-03-30T11:00:07+02:00)

- Guest `/help` is now part of the browser-proof lane instead of only the raw-route audit:
  - `scripts/e2e-hub-playwright.cjs` now visits `/help` in the guest browser flow, requires the stable help hero/fallback/privacy-boundary copy, and locks the live next-step links to `/downloads`, `/faq`, `/contact#support-intake`, and `/now`.
- Re-verified clean with:
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`

## Handoff refresh (2026-03-30T10:53:25+02:00)

- Public trust/legal surfaces now have browser-proof coverage instead of only raw-route checks:
  - `scripts/hub-live-audit.py` now treats `/faq`, `/privacy`, and `/terms` as richer release surfaces. The public audit now requires the FAQ search/next-step rails plus the privacy/terms policy-delta and action-link rails instead of stopping at route headings.
  - `scripts/e2e-hub-playwright.cjs` now visits `/faq`, `/privacy`, and `/terms` in the guest browser lane, verifies their customer-facing copy, and locks the critical action links (`/downloads`, `/help`, `/contact#support-intake`, `/now`) so those trust/legal surfaces can’t drift back to shallow or broken navigation.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T10:50:58+02:00)

- Guest participation routing is now canon-correct and release-blocking:
  - `Chummer.Run.Api/Controllers/PublicLandingController.cs` now resolves the signed-in participation lane on `/participate` through the actual current auth state instead of always forcing the authenticated route set. Guests now get the intended `/login?next=/participate/codex` and `/signup?next=/account/settings` handoffs, while signed-in users still keep the direct `/participate/codex` and `/account/settings` routes.
  - `scripts/hub-live-audit.py` and `scripts/e2e-hub-playwright.cjs` now treat `/what-is-chummer` and `/participate` as richer public release surfaces. The browser/live proof now requires the public story explainer rails plus the guest participation lane copy and guest-safe action hrefs.
  - `tests/RunServicesSmoke/Program.cs` now locks both participate states: guest routes must use login/signup-first handoffs, and authenticated routes must keep the direct participation/account paths.
- Integrated concurrent recap-shelf publication-trust view changes and repaired the broken contract so the repo stays green:
  - `Chummer.Run.Api/Views/Accounts/Account.cshtml` and `Chummer.Run.Api/Views/PublicLanding/Home.cshtml` were already carrying richer publication trust/discoverability rows on recap-shelf entries.
  - `Chummer.Campaign.Contracts/CampaignContracts.cs` now extends `PublicationSafeProjection` with the optional publication-trust fields those views already consume (`Audience`, `OwnershipSummary`, `PublicationState`, `TrustBand`, `Discoverable`, `PublicationSummary`, `CreatorPublicationId`, `NextSafeAction`), which clears the compile break that was failing `scripts/ai/run_services_smoke.sh` and `bash scripts/audit-compliance.sh`.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "RunServicesSmoke|PublicTrustPulseServiceTests|WeeklyProductPulseArtifactServiceTests"`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `bash scripts/run_smoke.sh`
  - `bash scripts/ai/run_services_smoke.sh`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`

## Handoff refresh (2026-03-30T10:43:28+02:00)

- The public front door now has release-blocking proof coverage for the full weekly trust pulse instead of only the hero/proof teaser:
  - `scripts/hub-live-audit.py` now fails `/` unless the rebuilt `chummer.run` landing route renders the full weekly pulse label set (`Who can get it now`, `Release proof`, `Launch readiness`, `Adoption health`, `Closure health`, `Progress trend`, `Journey pulse`, `Provider-route stewardship`, `Current caution`), the measured trend rail (`trust-pulse-trend__point`), and the `/now` plus `/progress` trust-pulse actions.
  - `scripts/e2e-hub-playwright.cjs` now enforces the same front-door pulse rows in the browser lane and requires at least two rendered `.trust-pulse-trend__point` elements on `/` so the landing trust pulse cannot silently collapse back to a thin summary block.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "RunServicesSmoke|PublicTrustPulseServiceTests|WeeklyProductPulseArtifactServiceTests"`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `bash scripts/run_smoke.sh`
  - `bash scripts/ai/run_services_smoke.sh`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`

## Handoff refresh (2026-03-30T10:11:48+02:00)

- Public roadmap and artifact detail pages are now part of the stronger public release-proof lane instead of only grazing their headings:
  - `scripts/hub-live-audit.py` now treats `/artifacts/current-preview-build` and `/roadmap/nexus-pan` as richer public proof surfaces and requires their real guidance rails (`Use and verify this proof`, `What this live artifact shows, who it helps, and what to check next`, `Start from the live surface`, `Open current release`, `Open support`, `Current pain, expected unlock, and the live proof you should compare first`, `Need a decision instead?`, `Compare with current proof`).
  - `scripts/e2e-hub-playwright.cjs` now enforces those same public detail-route rails in the browser lane and proves the honest next-step links back into `/now` and `/contact#support-intake` on both the live artifact page and the roadmap detail page.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T10:09:44+02:00)

- Signed-in participation is now part of the release-proof lane instead of only checking that `/participate/codex` exists:
  - `scripts/hub-live-audit.py` now treats the signed-in participation surface as release-blocking and requires the stable hero/journey/wizard contract (`Help Chummer show its work.`, `I want to participate`, `One decision, one code, one clean handoff`, `Generate fresh code`, `Open a fresh contribution lane`, `Technical details and controls`).
  - `scripts/e2e-hub-playwright.cjs` now opens the participation wizard and proves the real runtime state the local execution lane returns. It accepts the honest unavailable/complete branches, and on the actionable authorize-or-queued path it now requires the technical details rail, the one-time-code or queued-slot copy, and a clean stop path back to the `stopped` state.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T10:06:34+02:00)

- Signed-in profile and publication follow-through are now materially deeper and the publication deep-link instability is fixed:
  - `scripts/hub-live-audit.py` now treats `/account` as a release-blocking signed-in surface (`Display name`, `Handle`, `Timezone`, `Save profile`, `Primary sign-in`, `Recovery email`, `Start verification`) and it now requires creator-publication detail routes reached from both `home/work` and `account/work` to render the richer `Trust ranking` and `Discoverable now` rows.
  - `scripts/e2e-hub-playwright.cjs` now saves the signed-in profile with new values and proves they survive reload, opens the recovery-email drawer, completes the local preview verification round trip, and then requires `/account/advanced` to reflect the additional linked identity. The browser lane also now treats the creator-publication detail routes as release-blocking on the new trust/discoverability rows.
  - `Chummer.Campaign.Contracts/CampaignContracts.cs`, `Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs`, and `tests/RunServicesSmoke/Program.cs` now carry/lock `TrustBand` and `Discoverable` on recap-shelf entries so the shared home/work creator shelf can project the same trust posture into smoke and runtime proof.
  - `Chummer.Run.Api/Services/Community/CampaignSpineService.cs` no longer truncates creator-publication projections to the first three workspaces. That fixes the real runtime bug where workspace recap-shelf deep links could point at a publication that disappeared on the next request, which was why the selected publication detail route kept falling back out of the richer detail card.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `bash scripts/run_smoke.sh`
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "RunServicesSmoke"` (build/test discovery completed cleanly; the filter matched no individual test cases in `Chummer.Tests`)
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T09:54:53+02:00)

- Signed-in account settings and advanced proof are now materially deeper instead of only checking route headings:
  - `scripts/hub-live-audit.py` now treats `/account/settings` and `/account/advanced` as release-blocking signed-in surfaces. It requires the stable privacy/help-policy/account-metadata rows (`Visibility`, `Recovery posture`, `Provider-backed help`, `Open help`, `Read privacy`, `Read terms`, `Contact Chummer`, `Hub account id`, `Primary auth`, `Linked identities`, `Linked channels`, `Follow horizons`) before the broader work-journey audit is allowed to pass.
  - `scripts/e2e-hub-playwright.cjs` now makes the `/home/setup` wizard materially real by selecting a starter lane, saving the onboarding flow, and only then using `/account/settings` to prove that `Follow roadmap updates` and `Invite me when the right beta opens` can be saved and survive a reload. The browser lane also now verifies the signed-in help/privacy/terms/contact link cluster and the deeper `/account/advanced` metadata rail instead of stopping at surface headings.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/run_smoke.sh`
  - `bash scripts/audit-compliance.sh`

## Handoff refresh (2026-03-30T09:03:40+02:00)

- Integrated the concurrent first-playable-session proof expansion and brought the mirror/proof lane back to green:
  - `Chummer.Campaign.Contracts/CampaignContracts.cs`, `Chummer.Run.Api/Services/Community/CampaignSpineService.cs`, `Chummer.Run.Api/Views/PublicLanding/Home.cshtml`, `Chummer.Run.Api/Views/Accounts/Account.cshtml`, and `tests/RunServicesSmoke/Program.cs` now carry explicit first-session `RuleReadySummary`, `ReturnLaneSummary`, and `CampaignReadySummary` fields with customer-facing labels (`Legal runner`, `Understandable return`, `Campaign-ready lane`) on both the signed-in home and account work surfaces.
  - `scripts/hub-live-audit.py` and `scripts/e2e-hub-playwright.cjs` now require those new rows on the anchored first-playable-session route, so the shared first-session proof cannot drift out of the live/browser verification lane.
  - The mirrored [.codex-design/product/WEEKLY_PRODUCT_PULSE.generated.json](/docker/chummercomplete/chummer.run-services/.codex-design/product/WEEKLY_PRODUCT_PULSE.generated.json) was refreshed to restore `closure_health`, `adoption_health`, and `progress_trend` so the design mirror matches the live weekly pulse again.
- Re-verified clean with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "RunServicesSmoke|DesignMirrorExecutionPlanTests|PublicTrustPulseServiceTests|WeeklyProductPulseArtifactServiceTests"`
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:59:57+02:00)

- Signed-in home proof now treats the front-door overview and setup wizard as release-blocking instead of only grazing `/home/access` and `/home/work`:
  - `scripts/hub-live-audit.py` now requires `/home` to render the stable overview cards (`Welcome back`, `Use the current preview`, `Keep this copy connected`, `Open current release`) and `/home/setup` to carry the onboarding shell plus the three setup-step headings.
  - `scripts/e2e-hub-playwright.cjs` now opens `/home`, expands the `Build, explain, and next step` drawer, verifies the signed-in overview copy, then opens `/home/setup`, launches the onboarding dialog, walks through the three setup steps, and confirms the dialog can close cleanly without client-side errors.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:57:15+02:00)

- Signed-in support proof now covers every grounded assistant handoff the drawer is supposed to surface on the customer-visible route:
  - `scripts/hub-live-audit.py` now sends a signed-in rule-environment assistant query and fails unless the reply carries a `rules_truth` citation plus an `open_home` action, alongside the already-landed `build_truth`, `support_case`, `open_work`, and `open_account_support` checks.
  - `scripts/e2e-hub-playwright.cjs` now asks the same rule-environment question inside the `Need routing help first?` drawer, follows `Open home` into `/home`, and verifies the signed-in home overview renders `Welcome back`, `Build, explain, and next step`, and `What changed for me` before returning to the support route.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:55:46+02:00)

- Signed-in support proof now closes the assistant’s tracked-case loop instead of stopping at generic help/work routing:
  - `scripts/hub-live-audit.py` now creates a support case and immediately re-queries `/api/v1/support/cases/assistant` with that exact `caseId`, failing unless the response cites a `support_case` and offers the `open_account_support` timeline action.
  - `scripts/e2e-hub-playwright.cjs` now returns to `/account/support` after filing the uniquely titled case, reopens the assistant drawer, asks for that exact tracked case by title, requires the grounded answer and citation row, then verifies the signed-in history link still reopens the same detail route.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:54:20+02:00)

- Signed-in support proof now enforces the assistant’s grounded bridge back into the campaign/build work surface instead of only checking install/update help:
  - `scripts/hub-live-audit.py` now sends a signed-in support-assistant build-handoff query before case submission and fails unless the response carries at least one `build_truth` citation plus an `open_work` action.
  - `scripts/e2e-hub-playwright.cjs` now asks the same build-handoff question inside the `Need routing help first?` drawer, requires the grounded answer/citations, follows `Open work` into `/account/work`, verifies the work surface renders `Grounded rule answers` and `Build follow-through`, then returns to `/account/support` before filing the tracked case.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:52:33+02:00)

- Signed-in support proof now covers the calmer assistant rail and the rendered history loop instead of stopping at raw API assertions and the initial form redirect:
  - `scripts/hub-live-audit.py` now requires `/account/support` to render the assistant/form shell before case submission, then proves the tracked case title and detail link stay visible in the signed-in support history after notification and after reporter verification.
  - `scripts/e2e-hub-playwright.cjs` now opens the `Need routing help first?` drawer, submits a grounded install/update assistant query, follows the returned `Open downloads` action into the signed-in downloads surface, files a uniquely titled support case, returns to `/account/support`, and reopens the exact tracked case through the rendered history link.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:45:50+02:00)

- Signed-in access proof is now materially deeper instead of only checking route headings:
  - `scripts/hub-live-audit.py` now requires real account-access recovery/install evidence (`Recent install handoffs`, `Advanced device recovery`, `Offline-ready return`, the live linked-install host/version, and no leaked installation access token), plus a post-verification `home/access` pass that proves the support-closure card carries the actual audit case title, fixed version, affected install, and `Open downloads` next action.
  - `scripts/e2e-hub-playwright.cjs` now expands the `Release and device state` drawer on `/home/access`, verifies its release/device links, and expands the `Finish on another device`, `Advanced device recovery`, optional `Offline-ready return`, and `What stays on this device` drawers on `/account/access`.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:22:24+02:00)

- The anchored `home/work` operator rail now carries the rest of the modeled guided links as verified navigation instead of unproven CTA copy:
  - `scripts/hub-live-audit.py` now resolves and verifies the home-surface links for first playable session proof when present, plus the league rail, season board, invite rail, and sponsor rail. The new checks remain tolerant of the optional first-playable card while still enforcing the operator-anchor sections when they are rendered.
  - `scripts/e2e-hub-playwright.cjs` now navigates those same anchored routes in the browser lane, verifies the URL hash survives, and asserts the expected bounded section content on each destination surface.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:19:55+02:00)

- Signed-in `home/work` proof now follows the anchored return-lane and operator-guidance links instead of only asserting the CTA copy:
  - `scripts/hub-live-audit.py` now resolves the rendered anchor targets for next-session carry-forward, aftermath return, downtime brief, campaign memory, governed roster moves, and member guidance; it fetches the base route, verifies the target id exists, and requires the anchored section content to render. The live audit fetcher now retries transient request timeouts so the heavier signed-in route walk stays stable on the local edge.
  - `scripts/e2e-hub-playwright.cjs` now captures those same anchored `home/work` links, navigates to each one, verifies the URL hash is preserved, and asserts the expected bounded section content on the target signed-in route.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:15:57+02:00)

- Signed-in `home/work` proof now follows the advertised deep links instead of only asserting that the cards mention them:
  - `scripts/hub-live-audit.py` now extracts the rendered home-surface links for workspace detail, build follow-through, grounded rule answer, and publication status, then opens each route and requires the bounded detail cards to render.
  - `scripts/e2e-hub-playwright.cjs` now captures those same `home/work` links in the browser lane and asserts they land on the expected signed-in detail surfaces before continuing through the rest of the journey.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:13:34+02:00)

- Signed-in workspace-detail proof now exercises the governed prep-library search route instead of only checking the base workspace detail page:
  - `scripts/hub-live-audit.py` now opens `/account/work/workspaces/{workspaceId}?prepQuery=opposition`, requires non-empty search results, and confirms the prep-launch, travel-prefetch, aftermath, and carry-forward evidence remain visible after the query is applied.
  - `scripts/e2e-hub-playwright.cjs` now submits the `Search governed prep packets` form on the workspace detail page, verifies the normalized query stays in the route, and asserts the same evidence survives in the browser lane.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:12:02+02:00)

- Signed-in work proof now walks the modeled account-work detail routes for run context and grounded rule answers instead of leaving them covered only by in-process smoke:
  - `scripts/hub-live-audit.py` now extracts the first `/account/work/runs/{runId}` and `/account/work/rules/{entryId}` links from `/account/work`, opens both routes, and requires the run-context and grounded-rule detail cards to render their bounded evidence blocks.
  - `scripts/e2e-hub-playwright.cjs` now captures those same rendered links from `/account/work` and asserts both detail routes in the browser lane before continuing through the rest of the signed-in journey.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:06:16+02:00)

- Signed-in trust proof now treats the install-specific `Adoption health` row as release-blocking on `/downloads`, `/now`, and `/help`:
  - `scripts/hub-live-audit.py` now fails if those signed-in routes do not render `Adoption health` in both the install-specific trust panel and the weekly trust pulse.
  - `scripts/e2e-hub-playwright.cjs` now enforces the same minimum-count check in the browser lane.
- Creator-publication follow-through is now proven all the way into build-handoff detail instead of stopping at the publication page:
  - `scripts/hub-live-audit.py` now opens the first `/account/work/build-handoffs/{handoffId}` link from the publication-detail route and requires the rendered build follow-through posture.
  - `scripts/e2e-hub-playwright.cjs` now clicks through the same build-handoff link and asserts the destination route renders the expected follow-through card.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:00:33+02:00)

- The workspace artifact-shelf proof now follows the creator-publication deep link instead of only checking that the link exists:
  - `scripts/hub-live-audit.py` now extracts the first `/account/work/publications/{publicationId}` link from the signed-in workspace-detail shelf, opens it, and requires the rendered publication status, trust, discovery, and build-path follow-through.
  - `scripts/e2e-hub-playwright.cjs` now clicks the same publication-status link in the browser lane and asserts the destination route renders the publication-status card rather than leaving the deep link unproven.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T07:58:45+02:00)

- Signed-in hub proof now treats workspace artifact-shelf posture as release-blocking instead of only trusting the view source:
  - `scripts/hub-live-audit.py` now verifies the workspace-detail route reached from the signed-in journey renders artifact-shelf audience, ownership, publication posture, and publication-status deep links.
  - `scripts/e2e-hub-playwright.cjs` now expands the same workspace-detail artifact-shelf drawer in the browser lane and asserts the rendered ownership/publication posture there.
  - `tests/RunServicesSmoke/Program.cs` now locks the richer workspace-detail server-plane recap-shelf contract so in-process smoke fails if ownership/publication/next-safe-action posture disappears from the bound model.
- During this pass I explicitly confirmed that `/account/work` without a selected workspace does not hydrate `SelectedWorkspaceServerPlane`; the stable release-proof seam is `/account/work/workspaces/{workspaceId}`, and the hardened checks now target that route instead of the summary page.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `bash scripts/run_smoke.sh`
  - `bash scripts/ai/run_services_smoke.sh`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T07:25:00+02:00)

- The live audit now fails if `/api/public/weekly-pulse` stops reflecting Fleet-backed ready-state journey proof. It asserts:
  - `journey_gate_health.state == ready`
  - `journey_gate_health.blocked_count == 0`
  - presence of `supporting_signals.closure_health`, `adoption_health`, `progress_trend`, `provider_route_stewardship`, and `launch_readiness`
- The local public-edge compose lane now keeps a higher local write budget plus a small limiter queue (`CHUMMER_API_WRITE_RATE_LIMIT_PER_MINUTE=120`, `CHUMMER_API_RATE_LIMIT_QUEUE=16`) so signed-in audit and E2E traffic stops tripping avoidable local 429 backoff.
- `scripts/e2e-hub.sh` now uses explicit compose project names for both the edge stack and the Playwright runner, which removes the symlink-derived compose naming drift and isolates the browser lane from the edge project.
- The signed-in home aftermath card now surfaces recap-shelf ownership and publication state directly on `/home/work`, and smoke coverage now locks the new ownership/state shelf posture into both the home projection and registry preview/search checks.
- Re-verified clean with:
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

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
