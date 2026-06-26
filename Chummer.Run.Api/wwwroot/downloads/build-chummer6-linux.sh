#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_VERSION="1.3.0"
GITHUB_ORG="${CHUMMER_GITHUB_ORG:-ArchonMegalon}"
REPO_BASE_URL="${CHUMMER_REPO_BASE_URL:-https://github.com/$GITHUB_ORG}"
REPO_BASE_URL="${REPO_BASE_URL%/}"
GIT_REF="${CHUMMER_GIT_REF:-main}"
MIN_FREE_GIB="${CHUMMER_MIN_FREE_GIB:-25}"
DEFAULT_BASE="${CHUMMER_BUILD_BASE:-$HOME/chummer6-source-build}"
BASE_PATH=""
ASSUME_YES=0
AUDIT_ONLY=0
TOTAL_STEPS=11
CURRENT_STEP=0
START_SECONDS=$SECONDS
LOG_FILE=""
KEEP_BUILD_TEMP="${CHUMMER_KEEP_BUILD_TEMP:-0}"

usage() {
  cat <<'USAGE'
Build the Chummer6 Avalonia desktop client from source for this Linux computer.

Usage:
  ./build-chummer6-linux.sh [options]

Options:
  --base PATH          Workspace base path. Prompts when omitted.
  --ref REF            Git branch or tag for all repositories. Default: main.
  --yes, -y            Accepted for compatibility; no longer changes behavior.
  --skip-system-deps   Accepted for compatibility; the script never installs Linux system packages.
  --audit-only         Check this host and script setup without cloning or building.
  --help, -h           Show this help.

Environment overrides:
  CHUMMER_BUILD_BASE, CHUMMER_GIT_REF, CHUMMER_MIN_FREE_GIB,
  CHUMMER_GITHUB_ORG, CHUMMER_REPO_BASE_URL, CHUMMER_KEEP_BUILD_TEMP
USAGE
}

while (($#)); do
  case "$1" in
    --base)
      [[ $# -ge 2 ]] || { echo "--base requires a path" >&2; exit 2; }
      BASE_PATH="$2"
      shift 2
      ;;
    --ref)
      [[ $# -ge 2 ]] || { echo "--ref requires a value" >&2; exit 2; }
      GIT_REF="$2"
      shift 2
      ;;
    --yes|-y)
      ASSUME_YES=1
      shift
      ;;
    --skip-system-deps)
      shift
      ;;
    --audit-only)
      AUDIT_ONLY=1
      TOTAL_STEPS=3
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ "$MIN_FREE_GIB" =~ ^[0-9]+$ ]] || { echo "CHUMMER_MIN_FREE_GIB must be a whole number of GiB." >&2; exit 2; }

if [[ -z "$BASE_PATH" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Base path for Chummer6 source and build files [$DEFAULT_BASE]: " BASE_PATH
    BASE_PATH="${BASE_PATH:-$DEFAULT_BASE}"
  else
    BASE_PATH="$DEFAULT_BASE"
  fi
fi

if [[ "$BASE_PATH" == "~" ]]; then
  BASE_PATH="$HOME"
elif [[ "$BASE_PATH" == ~/* ]]; then
  BASE_PATH="$HOME/${BASE_PATH#~/}"
fi
mkdir -p "$BASE_PATH"
BASE_PATH="$(cd "$BASE_PATH" && pwd -P)"

mkdir -p "$BASE_PATH/logs"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$BASE_PATH/logs/linux-desktop-build-$RUN_ID.log"
exec > >(tee -a "$LOG_FILE") 2>&1

if [[ -t 1 ]]; then
  BOLD=$'\033[1m'
  GREEN=$'\033[32m'
  YELLOW=$'\033[33m'
  RED=$'\033[31m'
  RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi

log() {
  printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"
}

step() {
  CURRENT_STEP=$((CURRENT_STEP + 1))
  local percent=$((CURRENT_STEP * 100 / TOTAL_STEPS))
  printf '\n%s[%d/%d · %d%%] %s%s\n' "$BOLD" "$CURRENT_STEP" "$TOTAL_STEPS" "$percent" "$*" "$RESET"
}

warn() {
  printf '%sWARNING:%s %s\n' "$YELLOW" "$RESET" "$*" >&2
}

die() {
  printf '%sERROR:%s %s\n' "$RED" "$RESET" "$*" >&2
  exit 1
}

on_error() {
  local code=$?
  cleanup_build_temp || true
  printf '\n%sBuild failed%s at line %s with exit code %s.\n' "$RED" "$RESET" "$1" "$code" >&2
  printf 'Full log: %s\n' "$LOG_FILE" >&2
  exit "$code"
}
trap 'on_error "$LINENO"' ERR

cleanup_build_temp() {
  if [[ "${KEEP_BUILD_TEMP:-0}" == "1" || "${KEEP_BUILD_TEMP:-0}" == "true" || "${KEEP_BUILD_TEMP:-0}" == "yes" ]]; then
    return 0
  fi

  if [[ -n "${BASE_PATH:-}" && -d "$BASE_PATH/.tmp" ]]; then
    rm -rf "$BASE_PATH/.tmp"
  fi

  if [[ -n "${BASE_PATH:-}" && -d "$BASE_PATH" ]]; then
    find "$BASE_PATH" -mindepth 2 -maxdepth 2 -type d -name .tmp -prune -exec rm -rf {} +
  fi

  if [[ -n "${DOTNET_INSTALL:-}" && -f "$DOTNET_INSTALL" ]]; then
    rm -f "$DOTNET_INSTALL"
  fi
}

read_host_information() {
  DISTRO_ID="unknown"
  DISTRO_ID_LIKE=""
  DISTRO_VERSION="unknown"
  DISTRO_PRETTY="Unknown Linux"
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    DISTRO_ID="${ID:-unknown}"
    DISTRO_ID_LIKE="${ID_LIKE:-}"
    DISTRO_VERSION="${VERSION_ID:-unknown}"
    DISTRO_PRETTY="${PRETTY_NAME:-$DISTRO_ID $DISTRO_VERSION}"
  fi

  CPU_ARCH="$(uname -m)"
  case "$CPU_ARCH" in
    x86_64|amd64) RID="linux-x64" ;;
    aarch64|arm64) RID="linux-arm64" ;;
    *) die "Unsupported CPU architecture '$CPU_ARCH'. Supported: x86_64 and aarch64." ;;
  esac

  CPU_MODEL="unknown"
  if command -v lscpu >/dev/null 2>&1; then
    CPU_MODEL="$(lscpu | awk -F: '/Model name/ {sub(/^[ \t]+/, "", $2); print $2; exit}')"
  elif [[ -r /proc/cpuinfo ]]; then
    CPU_MODEL="$(awk -F: '/model name|Hardware/ {sub(/^[ \t]+/, "", $2); print $2; exit}' /proc/cpuinfo)"
  fi
  CPU_MODEL="${CPU_MODEL:-unknown}"
  CPU_CORES="$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 1)"
  MEMORY_KIB="$(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
  MEMORY_GIB=$((MEMORY_KIB / 1024 / 1024))

  if command -v getconf >/dev/null 2>&1 && getconf GNU_LIBC_VERSION >/dev/null 2>&1; then
    LIBC_INFO="$(getconf GNU_LIBC_VERSION)"
  else
    LIBC_INFO="$(ldd --version 2>&1 | head -1 || true)"
  fi
  if grep -qi musl <<<"$LIBC_INFO" || [[ -f /etc/alpine-release ]]; then
    die "This host uses musl/Alpine. The current Chummer6 desktop build targets glibc Linux."
  fi
}

choose_package_manager() {
  local all_ids=" $DISTRO_ID $DISTRO_ID_LIKE "
  if [[ "$all_ids" == *" debian "* || "$all_ids" == *" ubuntu "* || "$all_ids" == *" linuxmint "* ]] && command -v apt-get >/dev/null 2>&1; then
    printf 'apt'
  elif [[ "$all_ids" == *" fedora "* || "$all_ids" == *" rhel "* || "$all_ids" == *" centos "* || "$all_ids" == *" rocky "* || "$all_ids" == *" almalinux "* ]] && command -v dnf >/dev/null 2>&1; then
    printf 'dnf'
  elif [[ "$all_ids" == *" arch "* || "$all_ids" == *" manjaro "* ]] && command -v pacman >/dev/null 2>&1; then
    printf 'pacman'
  elif [[ "$all_ids" == *" suse "* || "$all_ids" == *" opensuse "* ]] && command -v zypper >/dev/null 2>&1; then
    printf 'zypper'
  elif command -v apt-get >/dev/null 2>&1; then printf 'apt'
  elif command -v dnf >/dev/null 2>&1; then printf 'dnf'
  elif command -v pacman >/dev/null 2>&1; then printf 'pacman'
  elif command -v zypper >/dev/null 2>&1; then printf 'zypper'
  else printf ''
  fi
}

check_required_commands() {
  local missing=()
  for command_name in git git-lfs curl tar gzip flock sha256sum file; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      missing+=("$command_name")
    fi
  done
  if ((${#missing[@]} == 0)); then
    return 0
  fi
  local manager
  manager="$(choose_package_manager)"
  local hint=""
  case "$manager" in
    apt) hint="Install them first, for example: apt-get install git git-lfs curl tar gzip unzip xz-utils util-linux file" ;;
    dnf) hint="Install them first, for example: dnf install git git-lfs curl tar gzip unzip xz util-linux file" ;;
    pacman) hint="Install them first, for example: pacman -S --needed git git-lfs curl tar gzip unzip xz util-linux file" ;;
    zypper) hint="Install them first, for example: zypper install git git-lfs curl tar gzip unzip xz util-linux file" ;;
    *) hint="Install the missing tools with your package manager, then rerun the script." ;;
  esac
  die "Missing required build tools: ${missing[*]}. $hint"
}

check_git_lfs_ready() {
  if ! git lfs version >/dev/null 2>&1; then
    die "Git LFS is required but not ready. Install git-lfs with your package manager, run 'git lfs install', then rerun the script."
  fi
}

dotnet_runtime_hint() {
  local manager
  manager="$(choose_package_manager)"
  case "$manager" in
    apt) printf '%s' "Install ICU first, for example: apt-get install libicu72 or the current libicu package for your distro." ;;
    dnf) printf '%s' "Install ICU first, for example: dnf install libicu." ;;
    pacman) printf '%s' "Install ICU first, for example: pacman -S --needed icu." ;;
    zypper) printf '%s' "Install ICU first, for example: zypper install libicu." ;;
    *) printf '%s' "Install the ICU runtime package for your distro, then rerun the script." ;;
  esac
}

check_local_dotnet_runtime() {
  local info_output=""
  if info_output="$(dotnet --info 2>&1)"; then
    printf '%s\n' "$info_output"
    return 0
  fi
  if grep -qi "Couldn't find a valid ICU package installed" <<<"$info_output"; then
    die "The local .NET SDK started, but this host is missing the ICU runtime needed by dotnet. $(dotnet_runtime_hint)"
  fi
  printf '%s\n' "$info_output" >&2
  die "The local .NET SDK could not start on this host. Check the log above, install the required runtime libraries, and rerun the script."
}

step "Inspecting this Linux host"
[[ "$(uname -s)" == "Linux" ]] || die "This script builds only the Linux desktop client."
read_host_information
log "Distribution: $DISTRO_PRETTY"
log "CPU: $CPU_MODEL"
log "Architecture: $CPU_ARCH → $RID"
log "Logical CPUs: $CPU_CORES"
log "Memory: ${MEMORY_GIB} GiB"
log "C library: $LIBC_INFO"
if (( MEMORY_GIB > 0 && MEMORY_GIB < 8 )); then
  warn "Less than 8 GiB RAM is available. The build may be slow or fail under memory pressure."
fi

step "Checking workspace permissions and free disk space"
mkdir -p "$BASE_PATH"
WRITE_TEST="$BASE_PATH/.chummer-write-test-$$"
printf 'ok\n' > "$WRITE_TEST"
rm -f "$WRITE_TEST"
EXEC_TEST="$BASE_PATH/.chummer-exec-test-$$.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$EXEC_TEST"
chmod +x "$EXEC_TEST"
if ! "$EXEC_TEST"; then
  rm -f "$EXEC_TEST"
  die "The selected base path is mounted noexec or cannot execute files: $BASE_PATH"
fi
rm -f "$EXEC_TEST"

AVAILABLE_KIB="$(df -Pk "$BASE_PATH" | awk 'NR==2 {print $4}')"
REQUIRED_KIB=$((MIN_FREE_GIB * 1024 * 1024))
[[ "$AVAILABLE_KIB" =~ ^[0-9]+$ ]] || die "Could not determine free disk space for $BASE_PATH"
if (( AVAILABLE_KIB < REQUIRED_KIB )); then
  AVAILABLE_GIB=$((AVAILABLE_KIB / 1024 / 1024))
  die "At least ${MIN_FREE_GIB} GiB free is required; only ${AVAILABLE_GIB} GiB is available at $BASE_PATH."
fi
log "Workspace: $BASE_PATH"
log "Git ref: $GIT_REF"
log "Free space: $((AVAILABLE_KIB / 1024 / 1024)) GiB"

step "Checking Linux build prerequisites"
PACKAGE_MANAGER="$(choose_package_manager)"
if [[ -n "$PACKAGE_MANAGER" ]]; then
  log "Detected package manager: $PACKAGE_MANAGER"
else
  warn "No supported package manager detected. Install prerequisites manually before the full build."
fi

if [[ "$AUDIT_ONLY" == "1" ]]; then
  for command_name in git git-lfs curl tar gzip flock sha256sum file; do
    if command -v "$command_name" >/dev/null 2>&1; then
      log "Found command: $command_name"
    else
      warn "Missing command for full build: $command_name"
    fi
  done
  ELAPSED=$((SECONDS - START_SECONDS))
  printf '\n%sAudit complete.%s\n' "$GREEN$BOLD" "$RESET"
  printf 'Host:      %s · %s · %s\n' "$DISTRO_PRETTY" "$CPU_ARCH" "$CPU_MODEL"
  printf 'Workspace: %s\n' "$BASE_PATH"
  printf 'Log:       %s\n' "$LOG_FILE"
  printf 'Elapsed:   %dm %ds\n' "$((ELAPSED / 60))" "$((ELAPSED % 60))"
  exit 0
fi

if [[ "$ASSUME_YES" == "1" ]]; then
  warn "--yes is accepted for compatibility, but the script no longer installs system packages."
fi
check_required_commands
check_git_lfs_ready
git lfs install --skip-repo >/dev/null

step "Cloning or updating the Chummer6 build repositories"
REPO_DIRS=(
  "chummer-core-engine"
  "chummer.run-services"
  "chummer-hub-registry"
  "chummer-ui-kit"
  "chummer6-ui"
)
REPO_NAMES=(
  "chummer6-core"
  "chummer6-hub"
  "chummer6-hub-registry"
  "chummer6-ui-kit"
  "chummer6-ui"
)

normalize_git_url() {
  local value="$1"
  value="${value%.git}"
  value="${value%/}"
  printf '%s' "$value"
}

sync_repo() {
  local directory_name="$1"
  local repository_name="$2"
  local target="$BASE_PATH/$directory_name"
  local expected_url="$REPO_BASE_URL/$repository_name.git"

  if [[ ! -e "$target" ]]; then
    log "Cloning $repository_name into $directory_name"
    git clone --depth 1 --filter=blob:none --branch "$GIT_REF" "$expected_url" "$target"
  else
    [[ -d "$target/.git" ]] || die "$target exists but is not a Git repository."
    local current_url
    current_url="$(git -C "$target" remote get-url origin)"
    if [[ "$(normalize_git_url "$current_url")" != "$(normalize_git_url "$expected_url")" ]]; then
      die "$target has unexpected origin '$current_url'; expected '$expected_url'."
    fi
    if [[ -n "$(git -C "$target" status --porcelain)" ]]; then
      die "$target has local changes. Commit, stash, or remove them before rerunning."
    fi
    log "Updating $repository_name"
    git -C "$target" fetch --depth 1 origin "$GIT_REF"
    git -C "$target" checkout -q --detach FETCH_HEAD
  fi

  if [[ -f "$target/.gitattributes" ]] && grep -q 'filter=lfs' "$target/.gitattributes"; then
    git -C "$target" lfs install --local >/dev/null
    git -C "$target" lfs pull
  fi
  if [[ -f "$target/.gitmodules" ]]; then
    git -C "$target" submodule update --init --recursive --depth 1
  fi
}

for index in "${!REPO_DIRS[@]}"; do
  sync_repo "${REPO_DIRS[$index]}" "${REPO_NAMES[$index]}"
done

step "Checking the cloned compatibility tree"
REQUIRED_FILES=(
  "$BASE_PATH/chummer6-ui/Chummer.Avalonia/Chummer.Avalonia.csproj"
  "$BASE_PATH/chummer6-ui/scripts/ai/with-package-plane.sh"
  "$BASE_PATH/chummer6-ui/scripts/ai/restore.sh"
  "$BASE_PATH/chummer6-ui/global.json"
  "$BASE_PATH/chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj"
  "$BASE_PATH/chummer-core-engine/Chummer.Application/Chummer.Application.csproj"
  "$BASE_PATH/chummer-core-engine/Chummer.Infrastructure/Chummer.Infrastructure.csproj"
  "$BASE_PATH/chummer-core-engine/Chummer.Rulesets.Hosting/Chummer.Rulesets.Hosting.csproj"
  "$BASE_PATH/chummer-core-engine/Chummer.Rulesets.Sr4/Chummer.Rulesets.Sr4.csproj"
  "$BASE_PATH/chummer-core-engine/Chummer.Rulesets.Sr5/Chummer.Rulesets.Sr5.csproj"
  "$BASE_PATH/chummer-core-engine/Chummer.Rulesets.Sr6/Chummer.Rulesets.Sr6.csproj"
  "$BASE_PATH/chummer.run-services/Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj"
  "$BASE_PATH/chummer.run-services/Chummer.Play.Contracts/Chummer.Play.Contracts.csproj"
  "$BASE_PATH/chummer.run-services/Chummer.Run.Contracts/Chummer.Run.Contracts.csproj"
  "$BASE_PATH/chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj"
  "$BASE_PATH/chummer-ui-kit/src/Chummer.Ui.Kit/Chummer.Ui.Kit.csproj"
)
for required_file in "${REQUIRED_FILES[@]}"; do
  [[ -f "$required_file" ]] || die "Required project file is missing: $required_file"
done
log "All required owner projects are present."

step "Installing the repository-pinned .NET SDK locally"
read_sdk_version() {
  local json_path="$1"
  sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$json_path" | head -1
}

SDK_VERSIONS=()
for json_file in \
  "$BASE_PATH/chummer6-ui/global.json" \
  "$BASE_PATH/chummer-core-engine/global.json" \
  "$BASE_PATH/chummer.run-services/global.json" \
  "$BASE_PATH/chummer-hub-registry/global.json" \
  "$BASE_PATH/chummer-ui-kit/global.json"; do
  if [[ -f "$json_file" ]]; then
    version="$(read_sdk_version "$json_file")"
    if [[ -n "$version" ]]; then
      SDK_VERSIONS+=("$version")
    fi
  fi
done

if (( ${#SDK_VERSIONS[@]} == 0 )); then
  die "Could not read any .NET SDK version from repository global.json files"
fi

SDK_VERSION="$(printf '%s\n' "${SDK_VERSIONS[@]}" | sort -V | tail -n 1)"
if [[ -n "${CHUMMER_SDK_VERSIONS_DEBUG:-}" ]]; then
  log "SDK versions seen: ${SDK_VERSIONS[*]}"
  log "Selected SDK version: $SDK_VERSION"
fi
DOTNET_DIR="$BASE_PATH/.tools/dotnet"
DOTNET_INSTALL="$BASE_PATH/.tools/dotnet-install.sh"
mkdir -p "$BASE_PATH/.tools"

if [[ ! -x "$DOTNET_DIR/dotnet" ]] || ! "$DOTNET_DIR/dotnet" --list-sdks 2>/dev/null | awk '{print $1}' | grep -Fxq "$SDK_VERSION"; then
  log "Installing .NET SDK $SDK_VERSION locally into $DOTNET_DIR"
  curl --fail --location --retry 5 --retry-delay 2 --proto '=https' --tlsv1.2 \
    https://dot.net/v1/dotnet-install.sh -o "$DOTNET_INSTALL"
  bash -n "$DOTNET_INSTALL"
  bash "$DOTNET_INSTALL" --version "$SDK_VERSION" --install-dir "$DOTNET_DIR" --no-path
else
  log ".NET SDK $SDK_VERSION is already installed in the workspace."
fi

export DOTNET_ROOT="$DOTNET_DIR"
export PATH="$DOTNET_DIR:$PATH"
export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_NOLOGO=1
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export AVALONIA_TELEMETRY_OPTOUT=1
export WRITABLE_STATE_ROOT="$BASE_PATH/.state"
export DOTNET_CLI_HOME="$BASE_PATH/.state/dotnet-cli"
export NUGET_PACKAGES="$BASE_PATH/.cache/nuget/packages"
export XDG_CACHE_HOME="$BASE_PATH/.cache/xdg"
export XDG_DATA_HOME="$BASE_PATH/.local/share"
export TMPDIR="$BASE_PATH/.tmp/runtime"
export CHUMMER_PACKAGE_PLANE_LOCK_ROOT="$BASE_PATH/.tmp/package-plane"
export CHUMMER_BOOTSTRAP_ENGINE_CONTRACTS_FEED=1
export CHUMMER_DESKTOP_UPDATE_MODE="${CHUMMER_DESKTOP_UPDATE_MODE:-notify}"
export CHUMMER_DESKTOP_ANALYTICS_DEFAULT="${CHUMMER_DESKTOP_ANALYTICS_DEFAULT:-off}"
mkdir -p "$DOTNET_CLI_HOME" "$NUGET_PACKAGES" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" "$TMPDIR" "$CHUMMER_PACKAGE_PLANE_LOCK_ROOT"
check_local_dotnet_runtime

step "Recording source revisions"
MANIFEST_DIR="$BASE_PATH/artifacts"
mkdir -p "$MANIFEST_DIR"
SOURCE_MANIFEST="$MANIFEST_DIR/source-revisions-$RUN_ID.txt"
{
  printf 'Chummer6 Linux desktop source build\n'
  printf 'Generated UTC: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'Script version: %s\n' "$SCRIPT_VERSION"
  printf 'Distribution: %s\n' "$DISTRO_PRETTY"
  printf 'CPU: %s\n' "$CPU_MODEL"
  printf 'Architecture: %s\n' "$CPU_ARCH"
  printf 'RID: %s\n' "$RID"
  printf '.NET SDK: %s\n' "$SDK_VERSION"
  printf 'Git ref: %s\n\n' "$GIT_REF"
  for index in "${!REPO_DIRS[@]}"; do
    printf '%-24s %s\n' "${REPO_NAMES[$index]}" "$(git -C "$BASE_PATH/${REPO_DIRS[$index]}" rev-parse HEAD)"
  done
} | tee "$SOURCE_MANIFEST"

step "Restoring NuGet packages and local compatibility contracts"
UI_ROOT="$BASE_PATH/chummer6-ui"
PROJECT="$UI_ROOT/Chummer.Avalonia/Chummer.Avalonia.csproj"
cd "$UI_ROOT"
bash scripts/ai/restore.sh "$PROJECT" \
  -r "$RID" \
  -p:TargetFramework=net10.0 \
  -p:ChummerUseLocalCompatibilityTree=true \
  -p:RestorePackagesPath="$NUGET_PACKAGES"

step "Publishing the self-contained desktop client for this host"
PUBLISH_DIR="$BASE_PATH/artifacts/chummer6-$RID"
rm -rf "$PUBLISH_DIR"
mkdir -p "$PUBLISH_DIR"
UI_SHA="$(git -C "$UI_ROOT" rev-parse --short=12 HEAD)"
SOURCE_VERSION="source-$UI_SHA-$RUN_ID"

bash scripts/ai/with-package-plane.sh publish "$PROJECT" \
  -c Release \
  -r "$RID" \
  --self-contained true \
  --verbosity minimal \
  -p:TargetFramework=net10.0 \
  -p:ChummerUseLocalCompatibilityTree=true \
  -p:PublishSingleFile=false \
  -p:PublishTrimmed=false \
  -p:PublishReadyToRun=false \
  -p:DebugType=None \
  -p:DebugSymbols=false \
  -p:UseAppHost=true \
  -p:ChummerDesktopReleaseChannel=source-build \
  -p:ChummerDesktopReleaseVersion="$SOURCE_VERSION" \
  -p:RestorePackagesPath="$NUGET_PACKAGES" \
  -o "$PUBLISH_DIR"

step "Verifying the published client and native library links"
BINARY="$PUBLISH_DIR/Chummer.Avalonia"
[[ -f "$BINARY" ]] || die "Publish completed but the executable was not created: $BINARY"
chmod +x "$BINARY"
file "$BINARY"
if command -v ldd >/dev/null 2>&1; then
  LDD_OUTPUT="$(ldd "$BINARY" 2>&1 || true)"
  printf '%s\n' "$LDD_OUTPUT"
  if grep -q 'not found' <<<"$LDD_OUTPUT"; then
    die "The client was built, but one or more native runtime libraries are missing. See the ldd output above."
  fi
fi

BINARY_SHA="$(sha256sum "$BINARY" | awk '{print $1}')"
BUILD_MANIFEST="$PUBLISH_DIR/BUILD-MANIFEST.txt"
{
  cat "$SOURCE_MANIFEST"
  printf '\nExecutable: Chummer.Avalonia\n'
  printf 'Executable SHA256: %s\n' "$BINARY_SHA"
  printf 'Output directory: %s\n' "$PUBLISH_DIR"
} > "$BUILD_MANIFEST"

cat > "$PUBLISH_DIR/run-chummer6.sh" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CHUMMER_DESKTOP_UPDATE_MODE="${CHUMMER_DESKTOP_UPDATE_MODE:-notify}"
export CHUMMER_DESKTOP_ANALYTICS_DEFAULT="${CHUMMER_DESKTOP_ANALYTICS_DEFAULT:-off}"
exec "$HERE/Chummer.Avalonia" "$@"
LAUNCHER
chmod +x "$PUBLISH_DIR/run-chummer6.sh"

step "Creating a portable source-build archive"
TARBALL="$BASE_PATH/artifacts/chummer6-$RID-$RUN_ID.tar.gz"
tar -C "$PUBLISH_DIR" -czf "$TARBALL" .
TARBALL_SHA="$(sha256sum "$TARBALL" | awk '{print $1}')"
printf '%s  %s\n' "$TARBALL_SHA" "$(basename "$TARBALL")" > "$TARBALL.sha256"
cleanup_build_temp

ELAPSED=$((SECONDS - START_SECONDS))
printf '\n%sBuild complete.%s\n' "$GREEN$BOLD" "$RESET"
printf 'Host:        %s · %s · %s\n' "$DISTRO_PRETTY" "$CPU_ARCH" "$CPU_MODEL"
printf 'Executable: %s\n' "$BINARY"
printf 'Launcher:   %s\n' "$PUBLISH_DIR/run-chummer6.sh"
printf 'Executable SHA256: %s\n' "$BINARY_SHA"
printf 'Archive:    %s\n' "$TARBALL"
printf 'Archive SHA256:    %s\n' "$TARBALL_SHA"
printf 'Manifest:   %s\n' "$BUILD_MANIFEST"
printf 'Log:        %s\n' "$LOG_FILE"
printf 'Elapsed:    %dm %ds\n' "$((ELAPSED / 60))" "$((ELAPSED % 60))"
