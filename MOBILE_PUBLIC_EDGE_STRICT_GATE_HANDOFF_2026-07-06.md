# Mobile Public-Edge Strict Gate Handoff

Updated: 2026-07-06T06:43:46+02:00

## Cross-Codex Refresh (2026-07-06T06:43:46+02:00)

- Read this first if you open this lane from another session.
- This file is still historical right now, not the current flagship blocker lane.
- Current canonical upstream truth remains:
  - `/docker/chummercomplete/chummer.run-services/.codex-studio/published/public-edge-browser-proofs/mobile-viewport/MOBILE_PWA_VIEWPORT_SMOKE.generated.json`
    - `status=pass`
  - `/docker/chummercomplete/chummer.run-services/.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
    - `status=pass`
  - `/docker/chummercomplete/RELEASE_BLOCKERS.generated.json`
    - only current blocker ids:
      - `release_posture:non_flagship_channel`
      - `release_truth:windows_installer_visual_audit`
  - `/docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json`
    - `startup_receipt_bundle_required=false`
    - remaining upstream gap is the promoted-digest Windows visual proof, not startup

- Read this to the other Codexes:
  - do not assign `/play` overflow work from the older sections below unless a fresh failing receipt appears
  - the active launch blockers are the preview release posture and the Windows visual-proof chain
  - keep this file as strict-lane history only

## Cross-Codex Refresh (2026-07-06T06:37:19+02:00)

- Read this first if you open this lane from another session.
- This file is historical right now, not the current flagship blocker lane.
- Current canonical upstream truth remains:
  - `/docker/chummercomplete/chummer.run-services/.codex-studio/published/public-edge-browser-proofs/mobile-viewport/MOBILE_PWA_VIEWPORT_SMOKE.generated.json`
    - `status=pass`
  - `/docker/chummercomplete/chummer.run-services/.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
    - `status=pass`
  - `/docker/chummercomplete/RELEASE_BLOCKERS.generated.json`
    - only current blocker ids:
      - `release_posture:non_flagship_channel`
      - `release_truth:windows_installer_visual_audit`

- Read this to the other Codexes:
  - do not assign `/play` overflow work from the older sections below unless a fresh failing receipt appears
  - the active launch blockers are the preview release posture and the Windows proof chain
  - keep this file as strict-lane history only

## Cross-Codex Refresh (2026-07-06T06:27:08+02:00)

- This lane is no longer the active blocker in the current published receipts.
- Current canonical lane receipts are now:
  - `/docker/chummercomplete/chummer.run-services/.codex-studio/published/public-edge-browser-proofs/mobile-viewport/MOBILE_PWA_VIEWPORT_SMOKE.generated.json`
    - `generated_at_utc=2026-07-06T04:22:17.992Z`
    - `status=pass`
  - `/docker/chummercomplete/chummer.run-services/.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
    - `generatedAtUtc=2026-07-06T04:24:54.011937+00:00`
    - `status=pass`
  - `/docker/chummercomplete/chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T04:26:13Z`
    - `summary.local_surface_all_passing=true`

- Interpretation for the other Codexes:
  - do not keep assigning `/play` overflow reduction from the older section below; that specific defect is cleared in the current published artifact
  - keep this file as history for the strict lane, but do not use its 06:12 blocker story as current runtime truth
  - the active flagship blockers are elsewhere now: preview release posture plus the external Windows proof chain

## Cross-Codex Refresh (2026-07-06T06:12:07+02:00)

- This lane has moved on from the older strict-lock/stale-postdeploy story below.
- The current canonical public-edge failure from the last full janitor run is:
  - `/docker/chummercomplete/chummer.run-services/.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
    - `generatedAtUtc=2026-07-06T04:03:28.029874+00:00`
    - `status=fail`
    - failure:
      - `mobile PWA viewport Playwright proof is not pass`
  - `/docker/chummercomplete/chummer.run-services/.codex-studio/published/public-edge-browser-proofs/mobile-viewport/MOBILE_PWA_VIEWPORT_SMOKE.generated.json`
    - `generated_at_utc=2026-07-06T04:02:39.093Z`
    - `status=fail`
    - exact defect:
      - `/play phone-390 has 130px horizontal overflow`

- Interpretation for the other Codexes:
  - the older sections below are still useful history, but they are not the current blocker shape
  - the active task is `/play` mobile overflow reduction, not foreign build-lock cleanup
  - do not call this lane green until the mobile viewport smoke flips to `pass` and the public-edge postdeploy gate flips to `pass`

- Suggested local rerun path once the layout fix lands:
  - `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --require-downloads-status-playwright --require-mobile-pwa-viewport-playwright --require-pwa-offline-cache-playwright --require-frontdoor-navigation-playwright --reuse-existing-playwright-artifacts --reuse-artifact-max-age-hours 24 --playwright-artifact-dir /docker/chummercomplete/chummer.run-services/.codex-studio/published/public-edge-browser-proofs/downloads-status --mobile-pwa-viewport-artifact-dir /docker/chummercomplete/chummer.run-services/.codex-studio/published/public-edge-browser-proofs/mobile-viewport --pwa-offline-cache-artifact-dir /docker/chummercomplete/chummer.run-services/.codex-studio/published/public-edge-browser-proofs/offline-cache --frontdoor-navigation-artifact-dir /docker/chummercomplete/chummer.run-services/.codex-studio/published/public-edge-browser-proofs/frontdoor-navigation --output /docker/chummercomplete/chummer.run-services/.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`

## Cross-Codex Refresh (2026-07-06T05:24:33+02:00)

- The `chummer-play` downstream verifier now explicitly checks the stale strict-postdeploy signal too, so this lane’s current blocker shape is pinned all the way into the local mobile release proof.
- Patched:
  - `/docker/chummercomplete/chummer-play/scripts/release/verify_mobile_release_proof.sh`
  - `/docker/chummercomplete/chummer-play/tests/test_mobile_cross_surface_refresh_contract.py`
- Focused verification passed:
  - `python3 -m unittest discover -s /docker/chummercomplete/chummer-play/tests -p 'test_mobile_cross_surface_refresh_contract.py'`
  - `bash -n /docker/chummercomplete/chummer-play/scripts/release/verify_mobile_release_proof.sh`
  - `python3 /docker/chummercomplete/chummer-play/scripts/materialize_mobile_local_release_proof.py`
  - `bash /docker/chummercomplete/chummer-play/scripts/release/verify_mobile_release_proof.sh`
    - result: `mobile release proof ok`

## Cross-Codex Refresh (2026-07-06T05:20:39+02:00)

- The lane-specific blocker truth is current again:
  - live relaxed/canonical public-edge proof is still green:
    - `/docker/chummercomplete/chummer.run-services/.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
    - `status=pass`
    - `generatedAtUtc=2026-07-06T01:43:39.373037+00:00`
    - `preflightStatus=pass`
    - `frontdoorNavigationPlayRoute=/mobile/player`
    - `readyMobileHandoffFrontdoorLaunchRoute=/mobile/player`
  - strict current preflight truth is blocked by active foreign build lanes:
    - `/tmp/chummer-public-edge-deploy-preflight-current.json`
    - `status=fail`
    - `generatedAtUtc=2026-07-06T03:16:40.365067+00:00`
    - current blocker findings:
      - `bash pid 2190701 matches build-chummer6-linux`
      - `bash pid 2201485 matches build-chummer6-linux`
  - the older strict postdeploy receipt on disk is now explicitly known stale relative to that current preflight:
    - `/tmp/chummer-public-edge-postdeploy-canonical-current.json`
    - `generatedAtUtc=2026-07-05T13:34:52.608371+00:00`
    - do not treat its old route/version/PWA failure family as current runtime truth until it is rerun

- The `chummer-play` consumer lane was hardened so it now reports that stale strict postdeploy state honestly instead of replaying the old product failures:
  - patched:
    - `/docker/chummercomplete/chummer-play/scripts/materialize_mobile_cross_surface_readiness.py`
    - `/docker/chummercomplete/chummer-play/scripts/materialize_mobile_local_release_proof.py`
    - `/docker/chummercomplete/chummer-play/tests/test_mobile_cross_surface_refresh_contract.py`
  - focused verification passed:
    - `python3 -m unittest discover -s /docker/chummercomplete/chummer-play/tests -p 'test_mobile_cross_surface_refresh_contract.py'`
    - `bash /docker/chummercomplete/chummer-play/scripts/release/verify_mobile_release_proof.sh`
  - current mobile receipt truth:
    - `.codex-studio/published/MOBILE_CROSS_SURFACE_READINESS.generated.json`
    - `status=fail`
    - `generated_at_utc=2026-07-06T03:19:11Z`
    - failures now narrowed to:
      - `strict public-edge preflight receipt is not pass`
      - `bash pid 2190701 matches build-chummer6-linux`
      - `bash pid 2201485 matches build-chummer6-linux`
      - `strict public-edge postdeploy receipt is older than the current strict preflight receipt`

## Cross-Codex Refresh (2026-07-06T05:13:39+02:00)

- This file remains a lane-specific blocker memo, not the top-level release-truth document.
- Canonical current truth for flagship blockers and current route-alias behavior is:
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
- Current verified live alias truth is:
  - `/player -> 302 /mobile/player`
  - `/gm -> 302 /mobile/gm`
  - `/observer -> 302 /mobile/observer`
- The strict public-edge blocker details below are still useful for this lane, but treat them as historical until the strict preflight and canonical postdeploy receipts are rerun.
- Release posture is still preview-only, and the missing promoted-digest Windows visual proof bundle remains a separate external blocker.
- Do not globally remove `/play?role=...` references from tests or fallback code. Some of them remain intentional failure fixtures for this exact gate family.

## Scope

This handoff is only about the external blocker that still prevents the mobile Blazor PWA from being promoted honestly. It does not claim ownership of the Windows proof lane, Google OAuth lane, or the rest of the flagship gold work already active in this repo.

## What changed for this lane

- `scripts/verify_public_edge_postdeploy_gate.py`
- `tests/test_public_edge_postdeploy_gate.py`

Behavioral hardening:

- the postdeploy receipt now records `skipPreflight`, `skipReleaseVersionMatch`, and `strictInvocation`
- `chummer-play` can now distinguish a relaxed live check from a true strict public-edge pass
- strict public-edge proof can no longer masquerade as green while foreign build-lock waivers are still active

## Proof already covered

Passed earlier in this session:

- `python3 -m pytest /docker/chummercomplete/chummer.run-services/tests/test_public_edge_postdeploy_gate.py`

The mobile repo then consumed this stricter receipt shape successfully through:

- `/docker/chummercomplete/chummer-play/tests/test_mobile_cross_surface_refresh_contract.py`
- `/docker/chummercomplete/chummer-play/scripts/materialize_mobile_cross_surface_readiness.py`

## Current blocker state

Strict preflight receipt currently on disk:

- `/tmp/chummer-public-edge-deploy-preflight-current.json`
  - `status=fail`
  - `generatedAtUtc=2026-07-05T13:32:03.805590+00:00`
  - `activeLockCount=2`
  - `foreignLockCount=2`
  - `staleForeignLockCount=2`
  - `allowForeignBuildLocks=false`
  - `allowStaleForeignBuildLocks=false`
  - blocker findings:
    - `bash pid 191868 matches build-chummer6-linux`
    - `bash pid 202947 matches build-chummer6-linux`
    - `overlay build info source fingerprint does not match current source: aggregateSha256, landing`

Strict canonical postdeploy receipt currently on disk:

- `/tmp/chummer-public-edge-postdeploy-canonical-current.json`
  - `status=fail`
  - `generatedAtUtc=2026-07-05T13:34:52.608371+00:00`
  - `preflightStatus=fail`
  - `preflightAllowForeignBuildLocks=true`
  - `preflightAllowStaleForeignBuildLocks=true`
  - `onlineLaunchStatus=pass`
  - `onlineLaunchFinalUrl=https://chummer.run/app?command=character_roster`
  - failure family still includes:
    - downloads version marker proof
    - public PWA static asset proof
    - ready mobile handoff proof
    - participate iframe shell proof
    - visible `/downloads` and `/status` version-marker drift

Live scan at handoff time shows the foreign-lock situation has moved but is still not clear:

- `202947 bash scripts/build-chummer6-linux.sh`
- `2201485 bash scripts/build-chummer6-linux.sh`

So the strict receipts are both failing and stale. They must be regenerated before anyone calls the mobile lane done.

## Boundaries

- Do not set `--skip-preflight` or `--skip-release-version-match` for the canonical strict receipt.
- Do not waive foreign build locks for the strict receipt.
- Do not collapse this into the Windows visual-proof blocker. They are separate lanes.
- Do not edit or revert unrelated flagship files in this repo; there is extensive parallel work in progress.

## Rerun sequence after the foreign build lanes clear

From `/docker/chummercomplete/chummer.run-services`:

1. `python3 scripts/check_public_edge_deploy_preflight.py --output /tmp/chummer-public-edge-deploy-preflight-current.json`
2. `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --output /tmp/chummer-public-edge-postdeploy-canonical-current.json`

Then tell the mobile lane to refresh:

1. `python3 /docker/chummercomplete/chummer-play/scripts/materialize_mobile_cross_surface_readiness.py`
2. `python3 /docker/chummercomplete/chummer-play/scripts/materialize_mobile_local_release_proof.py`

Success condition for this lane:

- preflight receipt `status=pass`
- canonical postdeploy receipt `status=pass`
- canonical postdeploy receipt proves `preflightStatus=pass`
- canonical postdeploy receipt shows `skipPreflight=false`, `skipReleaseVersionMatch=false`, and `strictInvocation=true`
