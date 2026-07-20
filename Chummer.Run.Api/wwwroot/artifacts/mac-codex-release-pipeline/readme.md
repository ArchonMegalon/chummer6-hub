# Mac Codex Release To chummer.run

Purpose: let a Codex session running on a Mac build a public-ready desktop artifact, prove it, and promote it onto the live `chummer.run` downloads shelf through the new authenticated HTTP upload endpoint instead of manual server file copies.

## Preferred operator entry points

Signed-in self-contained path:

1. Open `https://chummer.run/downloads/release-upload` in a signed-in browser.
2. In the Mac release shell, export a reviewed ref and exact full 40-hex commit pin for every source repository as shown below.
3. Copy the generated `Command` block from the page into that same shell.
4. When the Mac is ready, use `Mint and copy access code` on the page.
5. Run the command and paste the code at its hidden prompt.

That signed-in handoff is the source of truth for live publication because it serves the current hosted bootstrap, pins both the bootstrap and hosted proof digests in the one-liner, and mints the short-lived upload handoff only on demand. The command and rendered page never contain the code.
The bootstrap preserves reviewed repo refs supplied by the operator and requires their matching immutable commit pins, so the signed-in generated command, authenticated command endpoint, and repo-local wrapper paths all execute the same reviewed checkout plan.
The generated command intentionally does not invent or fetch commit pins. It stops before creating the release work root, cloning, building, or publishing when any pin is absent or is not exactly 40 hexadecimal characters.
Do not run `https://chummer.run/downloads/release-upload/bootstrap.sh` directly for live promotion; it can pass SHA-256 verification and still stop at upload time because a raw public script has no upload credential.
Do not put `ticket` or `apiToken` values in bootstrap URLs, command-line arguments, or shell history. A terminal curl does not inherit the browser sign-in session; copy the authenticated command from the page instead.

Use only refs and commits that were reviewed out of band. Do not derive these values from a dirty or unreviewed checkout:

```bash
export CHUMMER_UI_REF="<reviewed-ref>"
export CHUMMER_UI_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_CORE_REF="<reviewed-ref>"
export CHUMMER_CORE_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_HUB_REF="<reviewed-ref>"
export CHUMMER_HUB_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_UI_KIT_REF="<reviewed-ref>"
export CHUMMER_UI_KIT_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_HUB_REGISTRY_REF="<reviewed-ref>"
export CHUMMER_HUB_REGISTRY_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_MEDIA_FACTORY_REF="<reviewed-ref>"
export CHUMMER_MEDIA_FACTORY_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_LEGACY_REF="<reviewed-ref>"
export CHUMMER_LEGACY_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
```

Repo-local checkout path, if you already cloned `chummer.run-services` somewhere on the Mac:

```bash
repo_root="$(git rev-parse --show-toplevel)"
bash "$repo_root/scripts/run-mac-release-bootstrap.sh"
```

If one of the upload-auth `*_FILE` variants is set, the wrapper runs fully non-interactive and never prompts for input. Prefer an operator-owned, regular, non-symlink mode-`0600` file over exporting bearer plaintext.

```bash
ticket_file="$HOME/.chummer-release-upload-ticket"
install -m 600 /dev/null "$ticket_file"
printf 'Release upload access code: ' >&2
IFS= read -r -s ticket_value
printf '\n' >&2
printf '%s\n' "$ticket_value" > "$ticket_file"
unset ticket_value
export CHUMMER_RELEASE_UPLOAD_TICKET_FILE="$ticket_file"
repo_root="$(git rev-parse --show-toplevel)"
bash "$repo_root/scripts/run-mac-release-bootstrap.sh"
```

Do not hardcode `/docker/chummercomplete/.../bootstrap.sh` on the Mac host. That path only exists in provisioned Linux control environments, not on a normal release workstation.

## Governed local Mac candidate (stage only)

Use this lane when the Mac must produce a governed macOS candidate for later cross-platform assembly without touching an upload endpoint or public surface. It deliberately uses the repo-local wrapper, not the signed-in hosted `Command`: start from a clean `chummer.run-services` checkout pinned to a reviewed commit, and run from a clean shell with upload credentials, publish/remote-target settings, `CHUMMER_APP_SIGN_IDENTITY`, and `CHUMMER_NOTARY_PROFILE` unset. Stage-only mode rejects those settings instead of silently ignoring them.

Pin every cloned input with both its reviewed ref and exact 40-character commit before starting. Do not rely on a moving ref without its matching `*_EXPECTED_COMMIT`:

```bash
export CHUMMER_UI_REF="<reviewed-ref>"
export CHUMMER_UI_EXPECTED_COMMIT="<full-40-hex-commit>"
export CHUMMER_CORE_REF="<reviewed-ref>"
export CHUMMER_CORE_EXPECTED_COMMIT="<full-40-hex-commit>"
export CHUMMER_HUB_REF="<reviewed-ref>"
export CHUMMER_HUB_EXPECTED_COMMIT="<full-40-hex-commit>"
export CHUMMER_UI_KIT_REF="<reviewed-ref>"
export CHUMMER_UI_KIT_EXPECTED_COMMIT="<full-40-hex-commit>"
export CHUMMER_HUB_REGISTRY_REF="<reviewed-ref>"
export CHUMMER_HUB_REGISTRY_EXPECTED_COMMIT="<full-40-hex-commit>"
export CHUMMER_MEDIA_FACTORY_REF="<reviewed-ref>"
export CHUMMER_MEDIA_FACTORY_EXPECTED_COMMIT="<full-40-hex-commit>"
export CHUMMER_LEGACY_REF="<reviewed-ref>"
export CHUMMER_LEGACY_EXPECTED_COMMIT="<full-40-hex-commit>"
```

Use a fresh preview version that has never appeared on a candidate or public shelf. The output must be an absolute path whose parent exists and whose final directory does not exist or resolve through a symlink. If a run fails, choose a new version and output path instead of reusing either one:

```bash
repo_root="$(git rev-parse --show-toplevel)"
test -z "$(git -C "$repo_root" status --porcelain)" || {
  echo "refusing a dirty bootstrap checkout" >&2
  exit 1
}

release_version="run-$(date -u +%Y%m%d-%H%M%S)-mac-stage"
output="$HOME/chummer-release-candidates/$release_version"
mkdir -p "$(dirname "$output")"
test ! -e "$output" && test ! -L "$output" || {
  echo "stage-only output already exists" >&2
  exit 1
}

export CHUMMER_RELEASE_CHANNEL="preview"
export CHUMMER_RELEASE_VERSION="$release_version"
bash "$repo_root/scripts/run-mac-release-bootstrap.sh" \
  --stage-only \
  --stage-output-dir "$output"
```

This produces an unsigned preview candidate. It does not sign, notarize, upload, publish, activate, mutate a downloads shelf, or verify live surfaces. Before atomically placing the new output directory, the bootstrap revalidates the complete local bundle and its governed provenance. The candidate contains the macOS installer/archive bytes under `files/`, matching `RELEASE_CHANNEL.generated.json` and `releases.json`, digest-bound startup-smoke receipts, `release-evidence/public-promotion.json`, and `proof/build-provenance/v1/invocations/` plus `proof/build-provenance/v1/sbom/`. The provenance receipts bind the pinned source materials, executed bootstrap and build inputs, builder/target identity, SBOM, and final artifact bytes. `release-evidence/mac-stage-only.json` records `uploadAttempted=false`, `publicationAttempted=false`, `publicActivationAttempted=false`, and `countsAsPublicationEvidence=false`. Success prints `release_stage_only_path=<absolute path>`.

The Mac output is only a macOS slice. It must fail the canonical publisher's Linux/Windows/macOS platform floor if supplied by itself. On the integration host, first assemble that output with governed Linux and Windows outputs carrying the same fresh version and `preview` channel into a separate `full_candidate`. Then validate and seal that already complete input with the publisher's stage-only lane:

```bash
full_candidate="/absolute/path/to/governed-three-platform-input"
reference_shelf="/absolute/path/to/local-complete-reference-shelf"
validated_candidate="/absolute/path/to/new-validated-candidate"

CHUMMER_RELEASE_CANDIDATE_STAGE_ONLY=1 \
CHUMMER_RELEASE_CANDIDATE_OUTPUT_DIR="$validated_candidate" \
bash /absolute/path/to/chummer6-ui/scripts/publish-download-bundle.sh \
  "$full_candidate" \
  "$reference_shelf"
```

`validated_candidate` must also be absolute and nonexistent. This publisher mode validates the full canonical platform floor and governed provenance, writes only the new candidate directory, prints `release_candidate_stage_only_path=<absolute path>`, and leaves the reference shelf and all live/mirror targets unchanged. Promotion or activation is a later, separately authorized operation.

The hosted/bootstrap entry points above now:

1. preflights the live canonical manifest before creating the work root, cloning, restoring, building, or uploading
2. clones or updates the required repos under a local work root
3. builds both desktop heads by default: `avalonia` and `blazor-desktop`
4. packages one `.dmg` per head
5. codesigns, notarizes, staples, and validates them, or skips those steps for an explicit unsigned preview upload
6. runs startup smoke for each head
7. resolves or regenerates fresh release proof only after the candidate exists, using the reviewed Python runtime and a private per-run mutation lock under `$TMPDIR`
8. generates both `releases.json` and `RELEASE_CHANNEL.generated.json`, projects them to one caller-declared immutable generation, and records their exact byte digests
9. materializes a Registry-bound `review_required` authority envelope for that exact candidate and writes `release-evidence/public-promotion.json`
10. uploads every governed file through a durable session rooted at `https://chummer.run/api/internal/releases/upload-sessions`, then completes that same session exactly once
   - on any 400/401/403 upload response, the script prints parsed `Problem+JSON` fields plus `x-request-id` and actionable remediation hints.
11. rejects an upload response unless its generation id and both manifest digests exactly match the locally projected bytes
12. verifies immutable-generation routes first and all `CURRENT` release-facing routes second against the exact manifest and decision digests
13. records signed-in claim-code handoffs in the upload response and redacts them from stdout unless you explicitly opt in to print them
14. logs the executing bootstrap source path and SHA-256 so drift is visible in the transcript

The initial authority envelope is intentionally `review_required`; a successful upload is not by itself a `preview_ready`, stable, or gold claim. Installer availability remains fail-closed until the separately governed preview decision and postdeploy closure allow availability claims.

## What the bootstrap expects

Before running it, the Mac environment should already have:

1. Xcode Command Line Tools
2. `.NET 10`
3. `git`
4. Python 3.11 or newer (`python3.12` is preferred on the current Mac operator host)
5. `jq`
6. `curl`
7. Apple signing identity in the keychain for signed public-ready releases
8. `xcrun notarytool` credentials stored in a keychain profile for signed public-ready releases
9. a signed-in generated command from `/downloads/release-upload`, or an explicit upload ticket/token that is allowed to call the internal promotion endpoint

## Minimum environment variables

At minimum for signed public-ready releases:

```bash
export CHUMMER_APP_SIGN_IDENTITY="Developer ID Application: YOUR ORG (TEAMID)"
export CHUMMER_NOTARY_PROFILE="chummer-notary"
```

Required immutable source selection for both normal and stage-only runs, followed by optional overrides:

```bash
export CHUMMER_RELEASE_UPLOAD_SESSIONS_URL="https://chummer.run/api/internal/releases/upload-sessions"
export CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL="https://chummer.run/downloads/RELEASE_CHANNEL.generated.json"
export CHUMMER_RELEASE_UPLOAD_TICKET=""                # optional interactive handoff code override for non-prompted runs
export CHUMMER_RELEASE_UPLOAD_TICKET_FILE=""           # optional path to a one-line handoff code file
export CHUMMER_RELEASE_UPLOAD_TOKEN_FILE=""            # optional path to a one-line bearer token file
export CHUMMER_RELEASE_UPLOAD_TOKEN=""                 # optional explicit bearer token for CI or non-interactive runs
export CHUMMER_BOOTSTRAP_FORCE_LOCAL="0"               # set to 1 to force repo-local bootstrap execution (legacy behavior)
export CHUMMER_RELEASE_CHANNEL="preview"
export CHUMMER_RELEASE_GENERATION_ID=""              # optional reviewed safe id; normally generated once per candidate
export CHUMMER_RELEASE_SUPPORT_OWNER="Chummer release operations"
export CHUMMER_RELEASE_APP="avalonia,blazor-desktop"
export CHUMMER_RELEASE_RID="osx-arm64"
export CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK="0" # optional compatibility setting; true is rejected
export CHUMMER_RELEASE_UPLOAD_MAX_ATTEMPTS="4"
export CHUMMER_RELEASE_UPLOAD_RETRY_SLEEP_SECONDS="5"
export CHUMMER_UI_REF="<reviewed-ref>"
export CHUMMER_UI_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_CORE_REF="<reviewed-ref>"
export CHUMMER_CORE_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_HUB_REF="<reviewed-ref>"
export CHUMMER_HUB_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_UI_KIT_REF="<reviewed-ref>"
export CHUMMER_UI_KIT_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_HUB_REGISTRY_REF="<reviewed-ref>"
export CHUMMER_HUB_REGISTRY_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_MEDIA_FACTORY_REF="<reviewed-ref>"
export CHUMMER_MEDIA_FACTORY_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_LEGACY_REF="<reviewed-ref>"
export CHUMMER_LEGACY_EXPECTED_COMMIT="<full-40-hex-reviewed-commit>"
export CHUMMER_ALLOW_UNSIGNED_PREVIEW="1"
export CHUMMER_MAC_RELEASE_MIN_FREE_GIB="20"
export CHUMMER_MAC_RELEASE_TMPDIR="$HOME/chummer-release-tmp"
export CHUMMER_DESKTOP_INSTALLER_TMPDIR="$CHUMMER_MAC_RELEASE_TMPDIR/desktop-installer"
export CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE="0"
export CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION="0"
export CHUMMER_LIVE_CANONICAL_PREFLIGHT_TIMEOUT_SECONDS="30"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE=""      # optional explicit local release-proof JSON path
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH=""      # optional explicit local release-proof JSON path (preferred when precomputed)
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_BASE_URL="https://chummer.run"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_COMPOSE_FILE="./docker-compose.public-edge.yml"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_TIMEOUT_SECONDS="300"
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_SKIP_REBUILD="1"
export CHUMMER_HUB_LOCAL_PROOF_MUTATION_LOCK_PATH="" # optional; default is an owner-only per-run lock beneath $TMPDIR
export CHUMMER_UI_LOCALIZATION_RELEASE_GATE_FILE=""  # optional explicit UI localization gate JSON path
export CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH="/docker/chummercomplete/chummer-presentation-clean/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json"
export CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS="0" # leave all remote proof inputs disabled unless you intentionally opt into hosted proof files
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_URL=""        # optional remote proof URL when CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS=1
export CHUMMER_HUB_LOCAL_RELEASE_PROOF_EXPECTED_SHA256="" # required exact digest when the Hub proof URL is enabled
export CHUMMER_UI_LOCALIZATION_RELEASE_GATE_URL=""   # optional remote gate URL when CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS=1
export CHUMMER_UI_LOCALIZATION_RELEASE_GATE_EXPECTED_SHA256="" # required exact digest when the localization gate URL is enabled
```

Notes:

1. The bootstrap first checks the anonymous live canonical manifest. `stale` or `missing` proof freshness must be paired with `review_required` at the top-level, public-trust, and registry-boundary supportability paths. HTTP, network, malformed JSON, missing freshness, and unknown freshness failures stop before clone/build/upload and require an operator/deployment handoff. This preflight does not replace the final post-publish verification.
2. The bootstrap validates both local proof contracts before packaging and fails early if a supplied proof is stale, malformed, or missing required freshness fields.
3. The signed-in one-liner pins the hosted bootstrap SHA-256 before execution. Refresh the handoff page instead of bypassing the digest check.
4. The fetched bootstrap preserves caller-supplied reviewed refs, requires all seven exact 40-hex expected commits before normal or stage-only work begins, and fails closed if a fetched ref no longer resolves to its matching pin.
5. The bootstrap starts with `umask 077`, so temp files and directories default to operator-only permissions.
6. The signed-in handoff code is minted only when requested and is read by the generated command through a hidden prompt or a regular, non-symlink mode-`0600` file. It is not rendered into the page, fetched bootstrap, generated command, shell history, or child-process arguments.
7. Upload auth is streamed to curl through standard input and is never written to a curl config file or placed in `curl` argv. The cleanup trap is installed before any response or diagnostic temp file can be created and removes those non-credential files on success or failure.
8. `dist/release-upload-response.json` is sensitive because it can contain signed-in claim data. The bootstrap keeps it mode `0600`, prints only a strict non-secret response summary, and deletes the raw response by default unless `CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE=1`.
9. Local proof files are the default path. Remote proof or gate URLs are ignored unless `CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS=1`. When enabled, each configured URL also requires its matching `*_EXPECTED_SHA256`; the downloaded bytes are rejected before contract validation if the digest is absent, malformed, or mismatched.
10. If your run still fails this validation, export explicit known-good files:
   - `CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH` (from a trusted checked-in or freshly generated hub proof)
   - `CHUMMER_UI_LOCALIZATION_RELEASE_GATE_PATH` (from a trusted UI localization gate export)
11. The hosted bootstrap now defaults temporary packaging work to `$work_root/tmp` and exports `CHUMMER_DESKTOP_INSTALLER_TMPDIR="$TMPDIR/desktop-installer"` for `hdiutil`.
   - Override `CHUMMER_MAC_RELEASE_TMPDIR` when the default workspace volume is not the right disk for temporary DMG work.
   - Override `CHUMMER_DESKTOP_INSTALLER_TMPDIR` separately only when you intentionally want installer-image temp files on a different volume.
12. After a successful upload or a failed run, delete the local temporary release artifacts again so the Mac SSD does not fill up.
   - At minimum, clean the per-run work root under `$HOME/work/chummer-release/run-...` plus any custom `CHUMMER_MAC_RELEASE_TMPDIR` and `CHUMMER_DESKTOP_INSTALLER_TMPDIR` trees.
   - Keep those artifacts only while you are actively debugging a packaging, notarization, or upload failure.
13. Session creation and file/chunk staging retry bounded transient failures. Completion is never retried by the client: immediately before its single completion request, the bootstrap fsyncs an owner-only `dist/release-upload-handoff.json` in `request_started` state. That receipt binds the API origin, session ID, expiry, release version, canonical-manifest digest, exact inventory digest, byte/file counts, and monotonic state timestamps; it never contains a bearer credential, ticket, claim code, auth binding, or response body.
   - A completion transport error, response larger than `CHUMMER_RELEASE_UPLOAD_MAX_RESPONSE_BYTES` (default 1 MiB), or non-success response leaves the receipt `request_started`. Do not create another session; Fleet must call the recorded session's `/reconcile` route with managed internal authentication.
   - A successful completion is fsynced before the receipt moves to `completed`. Any later verifier failure prints an explicit already-published/unknown warning and forbids blind retry.
   - Direct multipart promotion is permanently disabled; any true `CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK` value is rejected.
14. Post-publish success is gated on the immutable generation first and the canonical `CURRENT` projection second. Both checks require the exact release version, manifest SHA-256, and release-decision SHA-256. `releases.json` is still fetched and checked, but compatibility drift is warning-only unless you set `CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION=1`. The server-returned probe URLs must match the canonical origin and exact governed current/generation download-route shapes before the bootstrap will request them.
15. Generator stderr is retained only as a bounded, credential-redacted diagnostic. Bearer values, token-like fields, JWT-shaped strings, and machine-local paths are removed before a failure is printed.

Single-head overrides are still supported:

```bash
export CHUMMER_RELEASE_APP="avalonia"
# or
export CHUMMER_RELEASE_APP="blazor-desktop"
```

## Automatic public result

When the upload succeeds, the exact candidate is installed as one immutable, authority-bound generation:

1. the promoted artifact is merged into the canonical live `https://chummer.run/downloads/RELEASE_CHANNEL.generated.json` shelf without dropping other platforms
2. `https://chummer.run/downloads/releases.json` remains coherent as the installer-oriented compatibility view
3. the server response must bind the caller-declared generation id and exact canonical/compatibility manifest digests
4. every public release-facing route must converge on the same authority snapshot and decision digest

The bootstrap seeds that generation as `review_required`. While it remains under review, the public pages may list the authority-bound artifacts, but the release-truth middleware withholds direct file and install handoffs. Those routes become usable only after a separate `preview_ready` decision is generated from the required scorecard and convergence evidence. Neither upload success nor a `preview_ready` decision is a stable/gold claim.

For macOS signed releases, the promoted artifact will only be visible publicly when the uploaded bundle includes:

1. startup-smoke receipts for the installer
2. `release-evidence/public-promotion.json`
3. `promotionStatus=pass`
4. `signingStatus=pass`
5. `notarizationStatus=pass`

For an operator-approved unsigned preview upload, set `CHUMMER_ALLOW_UNSIGNED_PREVIEW=1` and keep `CHUMMER_RELEASE_CHANNEL=preview`. That path skips codesign/notarization and uploads a preview DMG with `signingStatus=skipped_preview` and `notarizationStatus=skipped_preview`.

`CHUMMER_MAC_RELEASE_MIN_FREE_GIB` is enforced before clone/build work starts and again before temporary packaging work proceeds.
If the capacity preflight fails, the bootstrap writes `preflight-capacity-abort.json`; that receipt only explains why the run stopped and does not count as clone, packaging, startup-smoke, manifest, or upload evidence.

If a macOS ticket still reports `hdiutil: create failed - No space left on device`, rerun with `CHUMMER_MAC_RELEASE_TMPDIR` pointed at a workspace-backed path on the target SSD and clear old `run-*` directories under the same parent if they are no longer needed.

The same endpoint is platform-agnostic. A Windows bundle that carries the matching startup-smoke and signing proof can promote the Windows installer through the same route.

Every desktop release bundle now also carries a completed SR5 sample runner from `chummer5a/Chummer.Tests/TestFiles/Soma (Career).chum5`, staged inside the app under `Samples/Legacy/Soma-Career.chum5` so you can load it immediately after install.
