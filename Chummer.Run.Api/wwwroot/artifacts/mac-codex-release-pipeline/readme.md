# Mac Codex Release To chummer.run

Purpose: let a Codex session running on a Mac build a public-ready desktop artifact, prove it, and promote it onto the live `chummer.run` downloads shelf through the new authenticated HTTP upload endpoint instead of manual server file copies.

## Preferred operator entry points

Signed-in prompt-safe path:

1. Open `https://chummer.run/downloads/release-upload`
2. Copy the generated one-liner
3. Paste it into the Mac shell

That signed-in handoff is the source of truth for live publication because it serves the current hosted bootstrap, pins the bootstrap digest in the one-liner, and keeps the short-lived upload handoff code off the command line.
The bootstrap file itself now carries the pinned repo refs, so the signed-in, public curl, and repo-local wrapper paths all execute the same pinned checkout plan.

Public bootstrap path:

```bash
bash <(curl -fsSL https://chummer.run/downloads/release-upload/bootstrap.sh)
```

Repo-local checkout path, if you already cloned `chummer.run-services` somewhere on the Mac:

```bash
repo_root="$(git rev-parse --show-toplevel)"
bash "$repo_root/scripts/run-mac-release-bootstrap.sh"
```

Do not hardcode `/docker/chummercomplete/.../bootstrap.sh` on the Mac host. That path only exists in provisioned Linux control environments, not on a normal release workstation.

The hosted/bootstrap entry points above now:

1. clones or updates the required repos under a local work root
2. builds both desktop heads by default: `avalonia` and `blazor-desktop`
3. packages one `.dmg` per head
4. codesigns, notarizes, staples, and validates them, or skips those steps for an explicit unsigned preview upload
5. runs startup smoke for each head
6. generates both `releases.json` and `RELEASE_CHANNEL.generated.json` for the combined bundle
7. writes `release-evidence/public-promotion.json`
8. uploads the full bundle to `https://chummer.run/api/internal/releases/bundles`
   - on any 400/401/403 upload response, the script prints parsed `Problem+JSON` fields plus `x-request-id` and actionable remediation hints.
9. verifies the promoted public shelf and prints the live `/downloads/install/{artifactId}` handoff URLs
10. records signed-in claim-code handoffs in the upload response and redacts them from stdout unless you explicitly opt in to print them
11. logs the executing bootstrap source path and SHA-256 so drift is visible in the transcript

## What the bootstrap expects

Before running it, the Mac environment should already have:

1. Xcode Command Line Tools
2. `.NET 10`
3. `git`
4. `python3`
5. `jq`
6. `curl`
7. Apple signing identity in the keychain for signed public-ready releases
8. `xcrun notarytool` credentials stored in a keychain profile for signed public-ready releases
9. a signed-in release-upload handoff code or an explicit upload token that is allowed to call the internal promotion endpoint

## Minimum environment variables

At minimum for signed public-ready releases:

```bash
export CHUMMER_APP_SIGN_IDENTITY="Developer ID Application: YOUR ORG (TEAMID)"
export CHUMMER_NOTARY_PROFILE="chummer-notary"
```

Optional overrides:

```bash
export CHUMMER_RELEASE_UPLOAD_URL="https://chummer.run/api/internal/releases/bundles"
export CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL="https://chummer.run/downloads/RELEASE_CHANNEL.generated.json"
export CHUMMER_RELEASE_UPLOAD_TICKET=""                # optional interactive handoff code override for non-prompted runs
export CHUMMER_RELEASE_UPLOAD_TOKEN=""                 # optional explicit bearer token for CI or non-interactive runs
export CHUMMER_RELEASE_CHANNEL="preview"
export CHUMMER_RELEASE_APP="avalonia,blazor-desktop"
export CHUMMER_RELEASE_RID="osx-arm64"
export CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK="0"
export CHUMMER_RELEASE_UPLOAD_MAX_ATTEMPTS="4"
export CHUMMER_RELEASE_UPLOAD_RETRY_SLEEP_SECONDS="5"
export CHUMMER_UI_REF="main"
export CHUMMER_UI_EXPECTED_COMMIT=""
export CHUMMER_CORE_REF="main"
export CHUMMER_CORE_EXPECTED_COMMIT=""
export CHUMMER_HUB_REF="main"
export CHUMMER_HUB_EXPECTED_COMMIT=""
export CHUMMER_UI_KIT_REF="fleet/ui-kit"
export CHUMMER_UI_KIT_EXPECTED_COMMIT=""
export CHUMMER_HUB_REGISTRY_REF="main"
export CHUMMER_HUB_REGISTRY_EXPECTED_COMMIT=""
export CHUMMER_MEDIA_FACTORY_REF="main"
export CHUMMER_MEDIA_FACTORY_EXPECTED_COMMIT=""
export CHUMMER_LEGACY_REF="Docker"
export CHUMMER_LEGACY_EXPECTED_COMMIT=""
export CHUMMER_ALLOW_UNSIGNED_PREVIEW="1"
export CHUMMER_MAC_RELEASE_MIN_FREE_GIB="20"
export CHUMMER_MAC_RELEASE_TMPDIR="$HOME/chummer-release-tmp"
export CHUMMER_DESKTOP_INSTALLER_TMPDIR="$CHUMMER_MAC_RELEASE_TMPDIR/desktop-installer"
export CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE="0"
export CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION="0"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE=""      # optional explicit local release-proof JSON path
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH=""      # optional explicit local release-proof JSON path (preferred when precomputed)
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_BASE_URL="https://chummer.run"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_COMPOSE_FILE="./docker-compose.public-edge.yml"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_TIMEOUT_SECONDS="300"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_SKIP_REBUILD="1"
export CHUMMER_UI_LOCALIZATION_RELEASE_GATE_FILE=""  # optional explicit UI localization gate JSON path
export CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH="/docker/chummercomplete/chummer-presentation-clean/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json"
export CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS="0" # leave all remote proof inputs disabled unless you intentionally opt into hosted proof files
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_URL=""        # optional remote proof URL when CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS=1
export CHUMMER_UI_LOCALIZATION_RELEASE_GATE_URL=""   # optional remote gate URL when CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS=1

Notes:

1. The bootstrap validates both proof contracts before packaging and now fails early if a supplied proof is stale, malformed, or missing required freshness fields.
2. The signed-in one-liner pins the hosted bootstrap SHA-256 before execution. Refresh the handoff page instead of bypassing the digest check.
3. The fetched bootstrap now pins the repo refs to expected commits and fails closed if a fetched branch head no longer matches the signed-in handoff.
4. The bootstrap starts with `umask 077`, so temp files and directories default to operator-only permissions.
5. The signed-in handoff code is copied separately and pasted only when the bootstrap prompts for it, so it never lands in shell history or in the fetched bootstrap file.
6. Upload auth now goes through a `0600` temp curl config file without passing the token through a long-lived shell variable or `curl` argv entry.
7. `dist/release-upload-response.json` is sensitive because it can contain signed-in claim data. The bootstrap keeps it mode `0600` and deletes it by default after a successful run unless `CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE=1`.
8. Local proof files are the default path. Remote proof or gate URLs are ignored unless `CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS=1`.
9. If your run still fails this validation, export explicit known-good files:
   - `CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH` (from a trusted checked-in or freshly generated hub proof)
   - `CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH` (from a trusted UI localization gate export)
10. The hosted bootstrap now defaults temporary packaging work to `$work_root/tmp` and exports `CHUMMER_DESKTOP_INSTALLER_TMPDIR="$TMPDIR/desktop-installer"` for `hdiutil`.
   - Override `CHUMMER_MAC_RELEASE_TMPDIR` when the default workspace volume is not the right disk for temporary DMG work.
   - Override `CHUMMER_DESKTOP_INSTALLER_TMPDIR` separately only when you intentionally want installer-image temp files on a different volume.
11. If upload session requests return 4xx/5xx, upload now retries those requests first. Direct multipart promotion is available only when you opt in with `CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK=1`.
   - 400/401/403 responses are surfaced immediately with a parsed payload summary and stop-retry guidance.
12. Post-publish success is gated on the canonical `RELEASE_CHANNEL.generated.json` projection. `releases.json` is still fetched and checked, but compatibility drift is warning-only unless you set `CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION=1`.
``` 

Single-head overrides are still supported:

```bash
export CHUMMER_RELEASE_APP="avalonia"
# or
export CHUMMER_RELEASE_APP="blazor-desktop"
```

## Automatic public result

When the upload succeeds:

1. the promoted artifact is merged into the canonical live `https://chummer.run/downloads/RELEASE_CHANNEL.generated.json` shelf without dropping other platforms
2. `https://chummer.run/downloads/releases.json` remains coherent as the installer-oriented compatibility view
3. the direct file URLs become reachable under `/downloads/files/...`
4. the signed-in claim-code handoffs appear at `/downloads/install/{artifactId}`

For macOS signed releases, the promoted artifact will only be visible publicly when the uploaded bundle includes:

1. startup-smoke receipts for the installer
2. `release-evidence/public-promotion.json`
3. `promotionStatus=pass`
4. `signingStatus=pass`
5. `notarizationStatus=pass`

For an operator-approved unsigned preview upload, set `CHUMMER_ALLOW_UNSIGNED_PREVIEW=1` and keep `CHUMMER_RELEASE_CHANNEL=preview`. That path skips codesign/notarization and uploads a preview DMG with `signingStatus=skipped_preview` and `notarizationStatus=skipped_preview`.

`CHUMMER_MAC_RELEASE_MIN_FREE_GIB` is enforced before clone/build work starts and again before temporary packaging work proceeds.

If a macOS ticket still reports `hdiutil: create failed - No space left on device`, rerun with `CHUMMER_MAC_RELEASE_TMPDIR` pointed at a workspace-backed path on the target SSD and clear old `run-*` directories under the same parent if they are no longer needed.

The same endpoint is platform-agnostic. A Windows bundle that carries the matching startup-smoke and signing proof can promote the Windows installer through the same route.

Every desktop release bundle now also carries a completed SR5 sample runner from `chummer5a/Chummer.Tests/TestFiles/Soma (Career).chum5`, staged inside the app under `Samples/Legacy/Soma-Career.chum5` so you can load it immediately after install.
