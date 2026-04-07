# Mac Codex Release To chummer.run

Purpose: let a Codex session running on a Mac build a public-ready desktop artifact, prove it, and promote it onto the live `chummer.run` downloads shelf through the new authenticated HTTP upload endpoint instead of manual server file copies.

## Preferred operator entry points

Signed-in zero-touch path:

1. Open `https://chummer.run/downloads/release-upload`
2. Copy the generated one-liner
3. Paste it into the Mac shell

That signed-in handoff is the source of truth for live publication because it bakes in the short-lived upload ticket and always serves the current hosted bootstrap.

Public bootstrap path:

```bash
bash <(curl -fsSL https://chummer.run/artifacts/mac-codex-release-pipeline/bootstrap.sh)
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
10. prints signed-in claim codes for promoted artifacts when the upload ran with a signed-in release-upload ticket
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
9. a release-upload token that is allowed to call the internal promotion endpoint

## Minimum environment variables

At minimum:

```bash
export CHUMMER_APP_SIGN_IDENTITY="Developer ID Application: YOUR ORG (TEAMID)"
export CHUMMER_NOTARY_PROFILE="chummer-notary"
export CHUMMER_RELEASE_UPLOAD_TOKEN="..."
```

Optional overrides:

```bash
export CHUMMER_RELEASE_UPLOAD_URL="https://chummer.run/api/internal/releases/bundles"
export CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL="https://chummer.run/downloads/releases.json"
export CHUMMER_RELEASE_CHANNEL="preview"
export CHUMMER_RELEASE_APP="avalonia,blazor-desktop"
export CHUMMER_RELEASE_RID="osx-arm64"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_URL="https://chummer.run/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
export CHUMMER_UI_LOCALIZATION_RELEASE_GATE_URL="https://chummer.run/proofs/mac-codex-release/UI_LOCALIZATION_RELEASE_GATE.generated.json"
export CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK="1"
export CHUMMER_RELEASE_UPLOAD_MAX_ATTEMPTS="4"
export CHUMMER_RELEASE_UPLOAD_RETRY_SLEEP_SECONDS="5"
export CHUMMER_UI_REF="fleet/ui"
export CHUMMER_CORE_REF="fleet/core"
export CHUMMER_HUB_REF="main"
export CHUMMER_UI_KIT_REF="fleet/ui-kit"
export CHUMMER_HUB_REGISTRY_REF="fleet/hub-registry"
export CHUMMER_LEGACY_REF="Docker"
export CHUMMER_ALLOW_UNSIGNED_PREVIEW="1"
export CHUMMER_MAC_RELEASE_MIN_FREE_GIB="20"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE=""      # optional explicit local release-proof JSON path
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH=""      # optional explicit local release-proof JSON path (preferred when precomputed)
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_BASE_URL="https://chummer.run"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_COMPOSE_FILE="./docker-compose.public-edge.yml"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_TIMEOUT_SECONDS="300"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_SKIP_REBUILD="1"
export CHUMMER_UI_LOCALIZATION_RELEASE_GATE_FILE=""  # optional explicit UI localization gate JSON path
export CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH=""  # optional explicit UI localization gate JSON path (preferred)
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_URL=""       # optional override for hosted fallback proof URL
export CHUMMER_UI_LOCALIZATION_RELEASE_GATE_URL=""   # optional override for hosted fallback UI gate URL

Notes:

1. If either proof payload is missing/invalid, the bootstrap now validates both proof contracts before packaging and regenerates only the hub local proof as a fallback.
2. If local proof files are missing, the script now supports hosted proof URLs via the *_URL variables above and will download them automatically.
3. If your run still fails this validation, export explicit known-good files:
   - `CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH` (from a trusted checked-in or freshly generated hub proof)
   - `CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH` (from a trusted UI localization gate export)
4. If upload session requests return 4xx/5xx, upload now retries those requests and can fall back to direct multipart promotion when `CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK=1`.
   - 400/401/403 responses are surfaced immediately with a parsed payload summary and stop-retry guidance.
``` 

Single-head overrides are still supported:

```bash
export CHUMMER_RELEASE_APP="avalonia"
# or
export CHUMMER_RELEASE_APP="blazor-desktop"
```

## Automatic public result

When the upload succeeds:

1. the promoted artifact is merged into the live `https://chummer.run/downloads/releases.json` shelf without dropping other platforms
2. the direct file URLs become reachable under `/downloads/files/...`
3. the signed-in claim-code handoffs appear at `/downloads/install/{artifactId}`

For macOS signed releases, the promoted artifact will only be visible publicly when the uploaded bundle includes:

1. startup-smoke receipts for the installer
2. `release-evidence/public-promotion.json`
3. `promotionStatus=pass`
4. `signingStatus=pass`
5. `notarizationStatus=pass`

For an operator-approved unsigned preview upload, set `CHUMMER_ALLOW_UNSIGNED_PREVIEW=1` and keep `CHUMMER_RELEASE_CHANNEL=preview`. That path skips codesign/notarization and uploads a preview DMG with `signingStatus=skipped_preview` and `notarizationStatus=skipped_preview`.

`CHUMMER_MAC_RELEASE_MIN_FREE_GIB` is enforced before clone/build work starts and again before temporary packaging work proceeds.

The same endpoint is platform-agnostic. A Windows bundle that carries the matching startup-smoke and signing proof can promote the Windows installer through the same route.

Every desktop release bundle now also carries a completed SR5 sample runner from `chummer5a/Chummer.Tests/TestFiles/Soma (Career).chum5`, staged inside the app under `Samples/Legacy/Soma-Career.chum5` so you can load it immediately after install.
