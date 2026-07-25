#!/usr/bin/env bash
set -euo pipefail
export PATH=/usr/bin:/bin

if [[ "$#" -ne 7 ]]; then
  echo "usage: prepare_run_services_smoke.sh WORK_DIR CSC_DLL NETCORE_REF_DIR ASPNET_REF_DIR NETCORE_RUNTIME_VERSION ASPNET_RUNTIME_VERSION HOSTFXR_VERSION" >&2
  exit 2
fi

WORK_DIR="$1"
CSC_DLL="$2"
NETCORE_REF_DIR="$3"
ASPNET_REF_DIR="$4"
NETCORE_RUNTIME_VERSION="$5"
ASPNET_RUNTIME_VERSION="$6"
HOSTFXR_VERSION="$7"
if [[ ! -d "$WORK_DIR" || -L "$WORK_DIR" ]]; then
  echo "Campaign OS smoke work directory must be an existing non-symlink directory." >&2
  exit 1
fi
if [[ ! -d "$WORK_DIR/runtime" || -L "$WORK_DIR/runtime" || ! -d "$WORK_DIR/build" || -L "$WORK_DIR/build" ]]; then
  echo "Campaign OS smoke runtime and build directories must already exist." >&2
  exit 1
fi

script_dir="$(cd "$(dirname "$0")" && pwd -P)"
ROOT_DIR="$(cd "$script_dir/../.." && pwd -P)"
cd "$ROOT_DIR"

source "$script_dir/_env.sh"

EXPECTED_NUGET_PACKAGES="$ROOT_DIR/.tmp/nuget/packages"
if [[ "${CHUMMER_BUILD_NO_RESTORE:-}" != "1" ]]; then
  echo "Campaign OS proof preparation requires CHUMMER_BUILD_NO_RESTORE=1." >&2
  exit 1
fi
if [[ "${DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE:-}" != "1" ]]; then
  echo "Campaign OS proof preparation requires workload update notifications disabled." >&2
  exit 1
fi
if [[ "${NUGET_PACKAGES:-}" != "$EXPECTED_NUGET_PACKAGES" || ! -d "$EXPECTED_NUGET_PACKAGES" || -L "$EXPECTED_NUGET_PACKAGES" ]]; then
  echo "Campaign OS proof preparation requires the fixed existing local NuGet cache." >&2
  exit 1
fi

for required_source in \
  ../chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj \
  ../chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj \
  ../chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj \
  ../chummer-hub-registry/Chummer.Run.Registry/GlobalUsings.RegistryContracts.cs \
  ../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj \
  ../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime/Chummer.Media.Factory.Runtime.csproj \
  Chummer.Play.Contracts/Chummer.Play.Contracts.csproj \
  Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj \
  Chummer.Control.Contracts/Chummer.Control.Contracts.csproj \
  Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
  Chummer.World.Contracts/Chummer.World.Contracts.csproj \
  Chummer.Run.Api/Chummer.Run.Api.csproj \
  Chummer.Run.Identity/Chummer.Run.Identity.csproj \
  Chummer.Run.AI/Chummer.Run.AI.csproj \
  tests/RunServicesSmoke/Program.cs
do
  if [[ ! -f "$required_source" || -L "$required_source" ]]; then
    echo "missing required primary smoke source: $required_source" >&2
    exit 1
  fi
done


for project_spec in \
  "../chummer-core-engine/Chummer.Contracts|Chummer.Contracts.csproj" \
  "../chummer-hub-registry/Chummer.Hub.Registry.Contracts|Chummer.Hub.Registry.Contracts.csproj" \
  "../chummer-hub-registry/Chummer.Run.Registry|Chummer.Run.Registry.csproj" \
  "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts|Chummer.Media.Contracts.csproj" \
  "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime|Chummer.Media.Factory.Runtime.csproj" \
  "Chummer.Play.Contracts|Chummer.Play.Contracts.csproj" \
  "Chummer.Campaign.Contracts|Chummer.Campaign.Contracts.csproj" \
  "Chummer.Control.Contracts|Chummer.Control.Contracts.csproj" \
  "Chummer.Run.Contracts|Chummer.Run.Contracts.csproj" \
  "Chummer.World.Contracts|Chummer.World.Contracts.csproj" \
  "Chummer.Run.Api|Chummer.Run.Api.csproj" \
  "Chummer.Run.Identity|Chummer.Run.Identity.csproj" \
  "Chummer.Run.AI|Chummer.Run.AI.csproj"
do
  project_root="${project_spec%%|*}"
  project_file="${project_spec#*|}"
  for restore_input in \
    "$project_root/obj/project.assets.json" \
    "$project_root/obj/$project_file.nuget.g.props" \
    "$project_root/obj/$project_file.nuget.g.targets"
  do
    if [[ ! -f "$restore_input" || -L "$restore_input" ]]; then
      echo "missing fixed no-restore build input: $restore_input" >&2
      exit 1
    fi
  done
done

/usr/bin/bash --noprofile --norc "$script_dir/build_r1_cleanroom.sh" >/dev/null

RUNTIME_DIR="$WORK_DIR/runtime"
BUILD_DIR="$WORK_DIR/build"
resolve_artifact() {
  local label="$1"
  shift
  local candidate
  local lexical_path
  local resolved_path
  for candidate in "$@"; do
    lexical_path="$(/usr/bin/realpath -m -s -- "$candidate")"
    resolved_path="$(/usr/bin/readlink -f -- "$candidate" 2>/dev/null || true)"
    if [[ -f "$candidate" && ! -L "$candidate" && -n "$resolved_path" && "$resolved_path" == "$lexical_path" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  echo "missing required artifact for ${label}" >&2
  return 1
}

copy_artifact() {
  local label="$1"
  local output_name="$2"
  shift 2
  local source_path
  source_path="$(resolve_artifact "$label" "$@")" || return 1
  /usr/bin/python3 -I -S -c '
import os
import stat
import sys

source = os.path.abspath(sys.argv[1])
destination = os.path.abspath(sys.argv[2])
parts = source.split(os.sep)
if not source.startswith(os.sep) or any(part in ("", ".", "..") for part in parts[1:]):
    raise SystemExit("invalid artifact source path")
directory_fd = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY)
try:
    for component in parts[1:-1]:
        next_fd = os.open(
            component,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
        os.close(directory_fd)
        directory_fd = next_fd
    source_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        metadata = os.fstat(source_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
            raise SystemExit("artifact source is not a nonempty regular file")
        destination_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        try:
            while True:
                chunk = os.read(source_fd, 1024 * 1024)
                if not chunk:
                    break
                remaining = memoryview(chunk)
                while remaining:
                    written = os.write(destination_fd, remaining)
                    if written <= 0:
                        raise SystemExit("artifact destination write failed")
                    remaining = remaining[written:]
            os.fsync(destination_fd)
        finally:
            os.close(destination_fd)
    finally:
        os.close(source_fd)
finally:
    os.close(directory_fd)
' "$source_path" "$RUNTIME_DIR/$output_name"
}

DOTNET_HOST="/usr/bin/dotnet"
SDK_VERSION="$($DOTNET_HOST --version)"
DOTNET_ROOT="$(dirname "$(/usr/bin/readlink -f "$DOTNET_HOST")")"
EXPECTED_CSC="$DOTNET_ROOT/sdk/$SDK_VERSION/Roslyn/bincore/csc.dll"
if [[ "$CSC_DLL" != "$EXPECTED_CSC" || ! -f "$CSC_DLL" || -L "$CSC_DLL" ]]; then
  echo "resolved C# compiler does not match the fixed dotnet SDK." >&2
  exit 1
fi

require_exact_managed_directory() {
  local label="$1"
  local directory="$2"
  local lexical_path
  local resolved_path
  lexical_path="$(/usr/bin/realpath -m -s -- "$directory")"
  resolved_path="$(/usr/bin/readlink -f -- "$directory" 2>/dev/null || true)"
  if [[ ! -d "$directory" || -L "$directory" || -z "$resolved_path" || "$resolved_path" != "$lexical_path" ]]; then
    echo "invalid producer-selected managed directory for ${label}" >&2
    exit 1
  fi
}

NETCORE_REF_PREFIX="$DOTNET_ROOT/packs/Microsoft.NETCore.App.Ref/"
ASPNET_REF_PREFIX="$DOTNET_ROOT/packs/Microsoft.AspNetCore.App.Ref/"
NETCORE_REF_VERSION="${NETCORE_REF_DIR#"$NETCORE_REF_PREFIX"}"
NETCORE_REF_VERSION="${NETCORE_REF_VERSION%%/*}"
ASPNET_REF_VERSION="${ASPNET_REF_DIR#"$ASPNET_REF_PREFIX"}"
ASPNET_REF_VERSION="${ASPNET_REF_VERSION%%/*}"
if [[ "$NETCORE_REF_VERSION" != 10.* || "$ASPNET_REF_VERSION" != 10.* || "$NETCORE_REF_DIR" != "$NETCORE_REF_PREFIX$NETCORE_REF_VERSION/ref/net10.0" || "$ASPNET_REF_DIR" != "$ASPNET_REF_PREFIX$ASPNET_REF_VERSION/ref/net10.0" ]]; then
  echo "producer-selected reference directories are outside the exact .NET 10 pack roots" >&2
  exit 1
fi
require_exact_managed_directory "Microsoft.NETCore.App.Ref" "$NETCORE_REF_DIR"
require_exact_managed_directory "Microsoft.AspNetCore.App.Ref" "$ASPNET_REF_DIR"
require_exact_managed_directory "Microsoft.NETCore.App" "$DOTNET_ROOT/shared/Microsoft.NETCore.App/$NETCORE_RUNTIME_VERSION"
require_exact_managed_directory "Microsoft.AspNetCore.App" "$DOTNET_ROOT/shared/Microsoft.AspNetCore.App/$ASPNET_RUNTIME_VERSION"

if ! $DOTNET_HOST --list-runtimes | /usr/bin/awk -v expected="$NETCORE_RUNTIME_VERSION" '$1 == "Microsoft.NETCore.App" && $2 == expected { found = 1 } END { exit(found ? 0 : 1) }'; then
  echo "producer-selected Microsoft.NETCore.App runtime is not installed" >&2
  exit 1
fi
if ! $DOTNET_HOST --list-runtimes | /usr/bin/awk -v expected="$ASPNET_RUNTIME_VERSION" '$1 == "Microsoft.AspNetCore.App" && $2 == expected { found = 1 } END { exit(found ? 0 : 1) }'; then
  echo "producer-selected Microsoft.AspNetCore.App runtime is not installed" >&2
  exit 1
fi
EXPECTED_HOSTFXR_VERSION="$($DOTNET_HOST --info | /usr/bin/awk '/^Host:$/ { in_host = 1; next } in_host && /^[[:space:]]*Version:/ { print $2; exit }')"
if [[ -z "$EXPECTED_HOSTFXR_VERSION" ]]; then
  echo "unable to resolve installed .NET 10 references and runtimes" >&2
  exit 1
fi
if [[ "$HOSTFXR_VERSION" != "$EXPECTED_HOSTFXR_VERSION" ]]; then
  echo "producer-selected .NET closure does not match the fixed highest installed .NET 10 closure" >&2
  exit 1
fi

copy_artifact "Chummer.Play.Contracts" "Chummer.Play.Contracts.dll" \
  "Chummer.Play.Contracts/bin/Debug/net10.0/Chummer.Play.Contracts.dll"
copy_artifact "Chummer.Campaign.Contracts" "Chummer.Campaign.Contracts.dll" \
  "Chummer.Campaign.Contracts/bin/Debug/net10.0/Chummer.Campaign.Contracts.dll"
copy_artifact "Chummer.Control.Contracts" "Chummer.Control.Contracts.dll" \
  "Chummer.Control.Contracts/bin/Debug/net10.0/Chummer.Control.Contracts.dll"
copy_artifact "Chummer.World.Contracts" "Chummer.World.Contracts.dll" \
  "Chummer.World.Contracts/bin/Debug/net10.0/Chummer.World.Contracts.dll"
copy_artifact "Chummer.Engine.Contracts" "Chummer.Engine.Contracts.dll" \
  "../chummer-core-engine/Chummer.Contracts/bin/Debug/net10.0/Chummer.Engine.Contracts.dll"
copy_artifact "Chummer.Hub.Registry.Contracts" "Chummer.Hub.Registry.Contracts.dll" \
  "../chummer-hub-registry/Chummer.Hub.Registry.Contracts/bin/Debug/net10.0/Chummer.Hub.Registry.Contracts.dll"
copy_artifact "Chummer.Run.Registry" "Chummer.Run.Registry.dll" \
  "../chummer-hub-registry/Chummer.Run.Registry/bin/Debug/net10.0/Chummer.Run.Registry.dll"
copy_artifact "Chummer.Media.Contracts" "Chummer.Media.Contracts.dll" \
  "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/bin/Debug/net10.0/Chummer.Media.Contracts.dll"
copy_artifact "Chummer.Media.Factory.Runtime" "Chummer.Media.Factory.Runtime.dll" \
  "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime/bin/Debug/net10.0/Chummer.Media.Factory.Runtime.dll"
copy_artifact "Chummer.Run.Api" "Chummer.Run.Api.dll" \
  "Chummer.Run.Api/bin/Debug/net10.0/Chummer.Run.Api.dll"
copy_artifact "YamlDotNet" "YamlDotNet.dll" \
  "Chummer.Run.Api/bin/Debug/net10.0/YamlDotNet.dll"
copy_artifact "Chummer.Run.Identity" "Chummer.Run.Identity.dll" \
  "Chummer.Run.Identity/bin/Debug/net10.0/Chummer.Run.Identity.dll"
copy_artifact "Chummer.Run.AI" "Chummer.Run.AI.dll" \
  "Chummer.Run.AI/bin/Debug/net10.0/Chummer.Run.AI.dll"
copy_artifact "Chummer.Run.Contracts" "Chummer.Run.Contracts.dll" \
  "Chummer.Run.Contracts/bin/Debug/net10.0/Chummer.Run.Contracts.dll"

OUT_DLL="$RUNTIME_DIR/RunServicesSmoke.dll"
RSP_FILE="$BUILD_DIR/RunServicesSmoke.rsp"
{
  echo "-nologo"
  echo "-langversion:preview"
  echo "-nullable:enable"
  echo "-target:exe"
  echo "-out:${OUT_DLL}"
  for dll in "$NETCORE_REF_DIR"/*.dll; do
    echo "-r:${dll}"
  done
  for dll in "$ASPNET_REF_DIR"/*.dll; do
    echo "-r:${dll}"
  done
  for dll in "$RUNTIME_DIR"/Chummer*.dll; do
    echo "-r:${dll}"
  done
  echo "-r:${RUNTIME_DIR}/YamlDotNet.dll"
  echo "${ROOT_DIR}/../chummer-hub-registry/Chummer.Run.Registry/GlobalUsings.RegistryContracts.cs"
  echo "${ROOT_DIR}/tests/RunServicesSmoke/Program.cs"
} > "$RSP_FILE"

cat > "$RUNTIME_DIR/RunServicesSmoke.runtimeconfig.json" <<EOF
{
  "runtimeOptions": {
    "tfm": "net10.0",
    "frameworks": [
      { "name": "Microsoft.NETCore.App", "version": "${NETCORE_RUNTIME_VERSION}" },
      { "name": "Microsoft.AspNetCore.App", "version": "${ASPNET_RUNTIME_VERSION}" }
    ]
  }
}
EOF

"$DOTNET_HOST" "$CSC_DLL" @"$RSP_FILE"
test -s "$OUT_DLL"
