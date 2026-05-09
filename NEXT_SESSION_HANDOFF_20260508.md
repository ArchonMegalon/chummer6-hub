# Next session handoff - 2026-05-08

## What was completed

- Aligned the public `participate/codex` guest rail to the first-party login surface.
- Added a production startup guard so Hub now fails fast if Google OIDC is missing in `Production`.
- Hardened the Google callback path so the returned `id_token` is now required, signature-checked against Google JWKS, and cross-checked against `userinfo`.
- Fixed the release-upload bootstrap asset lookup so local and built Hub instances resolve the same `bootstrap.sh` template instead of 503ing.
- Removed remaining public-provider leakage from visible feedback/roadmap/changelog deep links and intake copy by renaming the public anchors and query parameter to first-party terms.
- Added an explicit compact-drawer account-actions label so the mobile nav source matches the signed-in rail and the public-surface trust test.
- Cleaned the last stale public-board wording out of the retry-expiry worker logs and the local M125 proof materializer.
- Tightened design/runtime truth where the repo was overstating SR6 readiness or understating SR4 host reality.
- Re-ran the focused public-surface and public-signal suite after those changes and closed the last local regression.

## Files changed

- `../chummer-design/products/chummer/PUBLIC_LANDING_MANIFEST.yaml`
- `../chummer-design/products/chummer/NEXT_12_BIGGEST_WINS_REGISTRY.yaml`
- `../chummer-design/products/chummer/NEXT_12_BIGGEST_WINS_GUIDE.md`
- `docs/PUBLIC_LANDING_SURFACE.md`
- `docs/HUB_IDENTITY_AND_CHANNEL_MODEL.md`
- `Chummer.Run.Api/Program.cs`
- `Chummer.Run.Api/Services/HubGoogleAuthService.cs`
- `Chummer.Run.Api/Controllers/CodexParticipationController.cs`
- `Chummer.Run.Api/Controllers/PublicLandingController.cs`
- `Chummer.Run.Api/Views/Shared/_Layout.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Participate.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Feedback.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Now.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Horizons.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Roadmap.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/Changelog.cshtml`
- `Chummer.Run.Api/Views/PublicLanding/KarmaForge.cshtml`
- `Chummer.Run.Api/Services/PublicSignalProjectionService.cs`
- `Chummer.Run.Api/Services/PublicSignalOperationsService.cs`
- `Chummer.Run.Api/Services/PublicSignalRetryExpiryWorker.cs`
- `Chummer.Run.Api/Services/Support/PublicSignalToCanonPacketService.cs`
- `Chummer.Run.Api/Services/Support/PrivacyBoundedSupportStatusService.cs`
- `Chummer.Run.Api/Services/Support/HostedProofContractService.cs`
- `scripts/hub-live-audit.py`
- `scripts/e2e-hub-playwright.cjs`
- `scripts/materialize_next90_m125_hub_public_signal_packets_proof.py`
- `scripts/verify_next90_m125_hub_public_signal_packets.py`
- `Chummer.Tests/PublicLandingReleaseTrustViewTests.cs`
- `Chummer.Tests/PublicSignalProjectionServiceTests.cs`
- `Chummer.Tests/PublicSignalOperationsServiceTests.cs`
- `Chummer.Tests/PublicSurfaceReferenceFilesTests.cs`
- `Chummer.Tests/PublicSignalToCanonPacketServiceTests.cs`
- `../chummer-core-engine/docs/SR4_ORACLE_EXTRACTION_MATRIX.md`
- `../Chummer6/DOWNLOAD.md`

## Local receipts captured

- Build:
  - `dotnet build Chummer.Run.Api/Chummer.Run.Api.csproj`
  - result: success, `0` warnings, `0` errors
- Syntax checks:
  - `python3 -m py_compile scripts/hub-live-audit.py scripts/verify_public_routes_from_manifest.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - result: both passed
- Focused tests:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "PublicSurfaceReferenceFilesTests|PublicSignalToCanonPacketServiceTests|PublicSignalProjectionServiceTests|PublicSignalOperationsServiceTests|PublicLandingReleaseTrustViewTests"`
  - result: passed `58/58` on both `net10.0` and `net10.0-windows`
- Local route proof:
  - generated file: `.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.local.generated.json`
  - result summary: `route_count=63`, `passed_count=63`, `failed_count=0`
- Local public-signal packet proof:
  - generated file: `.codex-studio/published/NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json`
  - result summary: materializer passed and rewrote the receipt with the first-party feedback wording
- Refreshed live canonical route proof:
  - generated file: `.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
  - result summary: `route_count=63`, `passed_count=62`, `failed_count=1`
  - remaining failure: `/participate/codex` still redirects live to `/auth/google/start?next=%2Fparticipate%2Fcodex` instead of `/login?next=%2Fparticipate%2Fcodex`
- Direct local checks:
  - `GET /participate/codex` redirects to `/login?next=%2Fparticipate%2Fcodex`
  - `GET /downloads/release-upload/bootstrap.sh` returns `200`
- Parity session state:
  - [parity-status.json](/docker/chummercomplete/chummer.run-services/adb70572c89e37eb1f5b2f8c420fbca174a21bbecd4a9637320682bf9b7524df/parity-status.json)
  - [work-package.json](/docker/chummercomplete/chummer.run-services/adb70572c89e37eb1f5b2f8c420fbca174a21bbecd4a9637320682bf9b7524df/work-package.json)
  - result summary: `parity_done=true`, `failing_count=0`, `active_slice=null`

## Parity status

- Repo-local parity is closed.
- No remaining parity slice is open in this repo.
- The only unresolved work left in this handoff is live-host validation, which is outside parity scope.

## Deferred non-parity live work

- `https://chummer.run` still exposes the old anonymous `/participate/codex` behavior in the live proof receipt.
  - current receipt: `.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
  - current live failure count: `1`
  - failing path: `/participate/codex`
- OAuth/account-linking still needs real end-to-end proof with live Google credentials and a deployed callback environment.

## Recommended first commands next session if live-host work resumes

1. Deploy the updated Hub build to the live `chummer.run` environment.
2. Re-run:
   - `python3 scripts/verify_public_routes_from_manifest.py --base-url https://chummer.run --manifest /docker/chummercomplete/chummer-design/products/chummer/PUBLIC_LANDING_MANIFEST.yaml --output .codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
3. If `/participate/codex` still misses after deploy, inspect the live deployment artifact or ingress/auth layer that is still sending anonymous traffic straight to Google instead of the first-party `/login` rail.
4. Run a live Google sign-in/linking proof with valid OIDC configuration and preserve the callback/receipt evidence.

## Notes

- Running the built Hub binary in `Production` without Google OIDC config now throws immediately by design.
- Running it in `Development` is the intended local proof mode for route verification without secrets.
- Scope is `chummer.run` only for live parity in this repo. Any old alias-host note should be treated as obsolete noise unless product direction changes.
