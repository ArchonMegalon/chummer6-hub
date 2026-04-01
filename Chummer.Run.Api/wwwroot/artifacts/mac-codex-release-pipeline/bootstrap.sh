#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[chummer-mac-release] %s\n' "$*"
}

die() {
  printf '[chummer-mac-release] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command missing: $1"
}

clone_or_update() {
  local repo_url="$1"
  local target_dir="$2"
  local ref="$3"

  if [[ -d "$target_dir/.git" ]]; then
    log "updating $(basename "$target_dir") -> $ref"
    git -C "$target_dir" fetch --depth 1 origin "$ref"
    git -C "$target_dir" checkout -q FETCH_HEAD
  else
    log "cloning $(basename "$target_dir") -> $ref"
    git clone --depth 1 --branch "$ref" "$repo_url" "$target_dir"
  fi
}

infer_publish_mode() {
  if [[ -n "${CHUMMER_RELEASE_PUBLISH_MODE:-}" ]]; then
    printf '%s' "$CHUMMER_RELEASE_PUBLISH_MODE"
    return
  fi

  if [[ -n "${CHUMMER_RELEASE_UPLOAD_URL:-}" || -n "${CHUMMER_RELEASE_UPLOAD_TOKEN:-}" ]]; then
    printf 'http'
    return
  fi

  if [[ -n "${CHUMMER_PORTAL_DOWNLOADS_S3_URI:-}" ]]; then
    printf 's3'
    return
  fi

  if [[ -n "${CHUMMER_RELEASE_SSH_TARGET:-}" && -n "${CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR:-}" ]]; then
    printf 'filesystem'
    return
  fi

  printf 'http'
}

is_true() {
  local value
  value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

main() {
  require_cmd git
  require_cmd dotnet
  require_cmd python3
  require_cmd jq
  require_cmd curl
  require_cmd hdiutil
  require_cmd ditto

  local work_root="${CHUMMER_MAC_RELEASE_WORK_ROOT:-$HOME/work/chummer-release}"
  local ui_ref="${CHUMMER_UI_REF:-fleet/ui}"
  local core_ref="${CHUMMER_CORE_REF:-fleet/core}"
  local hub_ref="${CHUMMER_HUB_REF:-main}"
  local ui_kit_ref="${CHUMMER_UI_KIT_REF:-fleet/ui-kit}"
  local registry_ref="${CHUMMER_HUB_REGISTRY_REF:-fleet/hub-registry}"
  local legacy_ref="${CHUMMER_LEGACY_REF:-Docker}"
  local app="${CHUMMER_RELEASE_APP:-avalonia}"
  local rid="${CHUMMER_RELEASE_RID:-osx-arm64}"
  local release_channel="${CHUMMER_RELEASE_CHANNEL:-preview}"
  local release_version="${CHUMMER_RELEASE_VERSION:-run-$(date -u +%Y%m%d-%H%M%S)}"
  local allow_unsigned_preview="${CHUMMER_ALLOW_UNSIGNED_PREVIEW:-0}"
  local publish_mode
  publish_mode="$(infer_publish_mode)"
  local verify_url="${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-https://chummer.run/downloads/releases.json}"
  local upload_url="${CHUMMER_RELEASE_UPLOAD_URL:-https://chummer.run/api/internal/releases/bundles}"

  local sign_identity="${CHUMMER_APP_SIGN_IDENTITY:-}"
  local notary_profile="${CHUMMER_NOTARY_PROFILE:-}"
  local require_signed_release=1
  if [[ -z "$sign_identity" || -z "$notary_profile" ]]; then
    if is_true "$allow_unsigned_preview" && [[ "$release_channel" == "preview" ]]; then
      require_signed_release=0
      log "Apple release credentials missing; continuing with unsigned preview upload."
    else
      [[ -n "$sign_identity" ]] || die "set CHUMMER_APP_SIGN_IDENTITY or CHUMMER_ALLOW_UNSIGNED_PREVIEW=1"
      [[ -n "$notary_profile" ]] || die "set CHUMMER_NOTARY_PROFILE or CHUMMER_ALLOW_UNSIGNED_PREVIEW=1"
    fi
  fi

  if [[ "$require_signed_release" == "1" ]]; then
    require_cmd xcrun
    require_cmd spctl
  fi

  local ui_repo="$work_root/r"
  local core_repo="$work_root/.c/core"
  local hub_repo="$work_root/.c/hub"
  local ui_kit_repo="$work_root/.c/ui"
  local registry_repo="$work_root/.c/registry"
  local legacy_repo="$work_root/.c/chummer5a"

  mkdir -p "$work_root" "$work_root/.c"

  clone_or_update "https://github.com/ArchonMegalon/chummer6-ui.git" "$ui_repo" "$ui_ref"
  clone_or_update "https://github.com/ArchonMegalon/chummer6-core.git" "$core_repo" "$core_ref"
  clone_or_update "https://github.com/ArchonMegalon/chummer6-hub.git" "$hub_repo" "$hub_ref"
  clone_or_update "https://github.com/ArchonMegalon/chummer6-ui-kit.git" "$ui_kit_repo" "$ui_kit_ref"
  clone_or_update "https://github.com/ArchonMegalon/chummer6-hub-registry.git" "$registry_repo" "$registry_ref"
  clone_or_update "https://github.com/ArchonMegalon/chummer5a.git" "$legacy_repo" "$legacy_ref"

  cd "$ui_repo"

  local project launch_target artifact_id artifact_kind
  case "$app" in
    avalonia)
      project="Chummer.Avalonia/Chummer.Avalonia.csproj"
      launch_target="Chummer.Avalonia"
      artifact_kind="dmg"
      artifact_id="avalonia-${rid}-dmg"
      ;;
    *)
      die "unsupported app head: $app"
      ;;
  esac

  export CHUMMER_LOCAL_CONTRACTS_PROJECT="$core_repo/Chummer.Contracts/Chummer.Contracts.csproj"
  export CHUMMER_LOCAL_RUN_CONTRACTS_PROJECT="$hub_repo/Chummer.Run.Contracts/Chummer.Run.Contracts.csproj"
  export CHUMMER_LOCAL_UI_KIT_PROJECT="$ui_kit_repo/src/Chummer.Ui.Kit/Chummer.Ui.Kit.csproj"
  export CHUMMER_HUB_REGISTRY_ROOT="$registry_repo"
  export CHUMMER_LEGACY_FIXTURE_ROOT="$legacy_repo/Chummer.Tests/TestFiles"

  local out_dir="out/$app/$rid"
  local dist_dir="dist"
  local dmg_path="$dist_dir/chummer-$app-$rid-installer.dmg"
  local smoke_dir="$dist_dir/startup-smoke"
  local evidence_dir="$dist_dir/release-evidence"
  local bundle_zip="$dist_dir/chummer-public-release-bundle.zip"
  local response_path="$dist_dir/release-upload-response.json"

  log "restoring $project for $rid"
  dotnet restore "$project" \
    -r "$rid" \
    -p:ChummerUseLocalCompatibilityTree=true \
    -p:ChummerLocalContractsProject="$CHUMMER_LOCAL_CONTRACTS_PROJECT" \
    -p:ChummerLocalRunContractsProject="$CHUMMER_LOCAL_RUN_CONTRACTS_PROJECT" \
    -p:ChummerLocalUiKitProject="$CHUMMER_LOCAL_UI_KIT_PROJECT"

  log "publishing $project"
  dotnet publish "$project" \
    -c Release \
    -r "$rid" \
    --self-contained true \
    -p:PublishSingleFile=true \
    -p:PublishTrimmed=false \
    -p:IncludeNativeLibrariesForSelfExtract=true \
    -p:ChummerUseLocalCompatibilityTree=true \
    -p:ChummerLocalContractsProject="$CHUMMER_LOCAL_CONTRACTS_PROJECT" \
    -p:ChummerLocalRunContractsProject="$CHUMMER_LOCAL_RUN_CONTRACTS_PROJECT" \
    -p:ChummerLocalUiKitProject="$CHUMMER_LOCAL_UI_KIT_PROJECT" \
    -p:ChummerDesktopReleaseVersion="$release_version" \
    -p:ChummerDesktopReleaseChannel="$release_channel" \
    -o "$out_dir"

  log "packaging dmg"
  bash scripts/build-desktop-installer.sh \
    "$out_dir" \
    "$app" \
    "$rid" \
    "$launch_target" \
    "$dist_dir" \
    "$release_version"

  [[ -f "$dmg_path" ]] || die "dmg not produced: $dmg_path"

  local signing_status="pass"
  local notarization_status="pass"
  if [[ "$require_signed_release" == "1" ]]; then
    log "repacking dmg with signed app bundle"
    local mount_dir repack_root app_bundle repacked_dmg
    mount_dir="$(mktemp -d "${TMPDIR:-/tmp}/chummer-mac-release-mount.XXXXXX")"
    repack_root="$(mktemp -d "${TMPDIR:-/tmp}/chummer-mac-release-repack.XXXXXX")"
    trap 'hdiutil detach "$mount_dir" >/dev/null 2>&1 || true; rm -rf "$mount_dir" "$repack_root"' EXIT

    hdiutil attach -nobrowse -readonly -mountpoint "$mount_dir" "$dmg_path" >/dev/null
    app_bundle="$(find "$mount_dir" -maxdepth 1 -type d -name '*.app' | sort | head -n 1)"
    [[ -n "$app_bundle" ]] || die "mounted dmg did not expose an .app bundle"
    cp -a "$app_bundle" "$repack_root/"
    hdiutil detach "$mount_dir" >/dev/null

    codesign --force --deep --options runtime --timestamp --sign "$sign_identity" "$repack_root/$(basename "$app_bundle")"

    repacked_dmg="${dmg_path%.dmg}-signed.dmg"
    rm -f "$repacked_dmg"
    hdiutil create \
      -volname "$(basename "$app_bundle" .app)" \
      -srcfolder "$repack_root" \
      -ov \
      -format UDZO \
      "$repacked_dmg" >/dev/null

    mv "$repacked_dmg" "$dmg_path"
    codesign --force --timestamp --sign "$sign_identity" "$dmg_path"

    log "notarizing dmg"
    xcrun notarytool submit "$dmg_path" --keychain-profile "$notary_profile" --wait
    xcrun stapler staple "$dmg_path"
    xcrun stapler validate "$dmg_path"
    spctl -a -vv --type open "$dmg_path" >/dev/null
  else
    signing_status="skipped_preview"
    notarization_status="skipped_preview"
    log "skipping codesign/notary for preview upload"
  fi

  mkdir -p "$smoke_dir"
  log "running mac startup smoke"
  CHUMMER_DESKTOP_RELEASE_CHANNEL="$release_channel" \
  CHUMMER_DESKTOP_RELEASE_VERSION="$release_version" \
  CHUMMER_DESKTOP_STARTUP_SMOKE_HOST_CLASS="${CHUMMER_DESKTOP_STARTUP_SMOKE_HOST_CLASS:-mac-codex-runner}" \
  bash scripts/run-desktop-startup-smoke.sh \
    "$dmg_path" \
    "$app" \
    "$rid" \
    "$launch_target" \
    "$smoke_dir" \
    "$release_version"

  mkdir -p "$dist_dir/files" "$evidence_dir"
  mv "$dmg_path" "$dist_dir/files/"

  local promoted_file="$dist_dir/files/$(basename "$dmg_path")"
  local published_at artifact_sha artifact_size
  published_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  artifact_sha="$(shasum -a 256 "$promoted_file" | awk '{print $1}')"
  artifact_size="$(stat -f '%z' "$promoted_file")"

  log "generating release manifests"
  STARTUP_SMOKE_DIR="$smoke_dir" \
  DOWNLOADS_DIR="$dist_dir/files" \
  MANIFEST_PATH="$dist_dir/releases.json" \
  PORTAL_MANIFEST_PATH="$dist_dir/releases.json" \
  CANONICAL_MANIFEST_PATH="$dist_dir/RELEASE_CHANNEL.generated.json" \
  PORTAL_CANONICAL_MANIFEST_PATH="$dist_dir/RELEASE_CHANNEL.generated.json" \
  RELEASE_VERSION="$release_version" \
  RELEASE_CHANNEL="$release_channel" \
  RELEASE_PUBLISHED_AT="$published_at" \
  bash scripts/generate-releases-manifest.sh

  cat > "$evidence_dir/public-promotion.json" <<EOF
{
  "contractName": "chummer.run.desktop_release_publication",
  "generatedAt": "$published_at",
  "artifacts": [
    {
      "artifactId": "$artifact_id",
      "fileName": "$(basename "$promoted_file")",
      "platform": "macos",
      "promotionStatus": "pass",
      "startupSmokeStatus": "pass",
      "signingStatus": "$signing_status",
      "notarizationStatus": "$notarization_status",
      "artifactSha256": "$artifact_sha",
      "artifactSizeBytes": $artifact_size,
      "kind": "$artifact_kind"
    }
  ]
}
EOF

  case "$publish_mode" in
    http)
      local upload_token="${CHUMMER_RELEASE_UPLOAD_TOKEN:-${FLEET_INTERNAL_API_TOKEN:-}}"
      [[ -n "$upload_token" ]] || die "set CHUMMER_RELEASE_UPLOAD_TOKEN for HTTP release promotion"
      log "packing release bundle"
      rm -f "$bundle_zip"
      ditto -c -k "$dist_dir" "$bundle_zip"
      log "uploading release bundle to $upload_url"
      curl --fail-with-body -sS \
        -X POST \
        -H "Authorization: Bearer $upload_token" \
        -F "bundle=@${bundle_zip};type=application/zip" \
        "$upload_url" \
        > "$response_path"
      jq . "$response_path"
      ;;
    filesystem)
      require_cmd ssh
      require_cmd rsync
      [[ -n "${CHUMMER_RELEASE_SSH_TARGET:-}" ]] || die "set CHUMMER_RELEASE_SSH_TARGET for filesystem publish"
      [[ -n "${CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR:-}" ]] || die "set CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR for filesystem publish"
      local remote_stage="${CHUMMER_REMOTE_STAGING_DIR:-/tmp/chummer-mac-release-bundle}"
      local remote_ui_repo="${CHUMMER_REMOTE_UI_REPO_DIR:-/docker/chummercomplete/chummer6-ui}"
      log "syncing bundle to ${CHUMMER_RELEASE_SSH_TARGET}:${remote_stage}"
      rsync -az --delete "$dist_dir/" "${CHUMMER_RELEASE_SSH_TARGET}:${remote_stage}/"
      log "publishing bundle on remote host"
      ssh "$CHUMMER_RELEASE_SSH_TARGET" \
        "cd '$remote_ui_repo' && bash scripts/publish-download-bundle.sh '$remote_stage' '${CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR}'"
      ;;
    s3)
      require_cmd aws
      [[ -n "${CHUMMER_PORTAL_DOWNLOADS_S3_URI:-}" ]] || die "set CHUMMER_PORTAL_DOWNLOADS_S3_URI for s3 publish"
      log "publishing bundle to object storage"
      CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL="$verify_url" bash scripts/publish-download-bundle-s3.sh "$dist_dir"
      ;;
    *)
      die "unsupported publish mode: $publish_mode"
      ;;
  esac

  log "verifying local bundle manifest"
  bash scripts/verify-releases-manifest.sh "$dist_dir/releases.json"

  log "verifying live manifest at $verify_url"
  bash scripts/verify-releases-manifest.sh "$verify_url"

  if [[ -f "$response_path" ]]; then
    log "public downloads url: $(jq -r '.downloadsUrl // empty' "$response_path")"
    jq -r '.installDispatchUrls[]? | "install handoff: " + .' "$response_path"
    jq -r '.directFileUrls[]? | "direct file: " + .' "$response_path"
    jq -r '.signedInInstallClaims[]? | "claim code: " + .artifactId + " -> " + .claimCode + " (dispatch: " + .installDispatchUrl + ")"' "$response_path"
  fi

  log "done"
}

main "$@"
