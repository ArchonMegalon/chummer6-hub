# Mac Codex Release To chummer.run

Purpose: let a Codex session running on a Mac build a public-ready desktop artifact, prove it, and promote it onto the live `chummer.run` downloads shelf through the new authenticated HTTP upload endpoint instead of manual server file copies.

## One command

Paste this into the Mac shell:

```bash
bash <(curl -fsSL https://chummer.run/artifacts/mac-codex-release-pipeline/bootstrap.sh)
```

That bootstrap script now:

1. clones or updates the required repos under a local work root
2. builds the desktop head
3. packages a `.dmg`
4. codesigns, notarizes, staples, and validates it, or skips those steps for an explicit unsigned preview upload
5. runs startup smoke
6. generates both `releases.json` and `RELEASE_CHANNEL.generated.json`
7. writes `release-evidence/public-promotion.json`
8. uploads the full bundle to `https://chummer.run/api/internal/releases/bundles`
9. verifies the promoted public shelf and prints the live `/downloads/install/{artifactId}` handoff URL
10. prints signed-in claim codes for promoted artifacts when the upload ran with a signed-in release-upload ticket

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
export CHUMMER_RELEASE_APP="avalonia"
export CHUMMER_RELEASE_RID="osx-arm64"
export CHUMMER_UI_REF="fleet/ui"
export CHUMMER_CORE_REF="fleet/core"
export CHUMMER_HUB_REF="main"
export CHUMMER_UI_KIT_REF="fleet/ui-kit"
export CHUMMER_HUB_REGISTRY_REF="fleet/hub-registry"
export CHUMMER_LEGACY_REF="Docker"
export CHUMMER_ALLOW_UNSIGNED_PREVIEW="1"
```

## Automatic public result

When the upload succeeds:

1. the promoted artifact is merged into the live `https://chummer.run/downloads/releases.json` shelf without dropping other platforms
2. the direct file URL becomes reachable under `/downloads/files/...`
3. the signed-in claim-code handoff appears at `/downloads/install/{artifactId}`

For macOS signed releases, the promoted artifact will only be visible publicly when the uploaded bundle includes:

1. startup-smoke receipts for the installer
2. `release-evidence/public-promotion.json`
3. `promotionStatus=pass`
4. `signingStatus=pass`
5. `notarizationStatus=pass`

For an operator-approved unsigned preview upload, set `CHUMMER_ALLOW_UNSIGNED_PREVIEW=1` and keep `CHUMMER_RELEASE_CHANNEL=preview`. That path skips codesign/notarization and uploads a preview DMG with `signingStatus=skipped_preview` and `notarizationStatus=skipped_preview`.

The same endpoint is platform-agnostic. A Windows bundle that carries the matching startup-smoke and signing proof can promote the Windows installer through the same route.

Every desktop release bundle now also carries a completed SR5 sample runner from `chummer5a/Chummer.Tests/TestFiles/Soma (Career).chum5`, staged inside the app under `Samples/Legacy/Soma-Career.chum5` so you can load it immediately after install.
