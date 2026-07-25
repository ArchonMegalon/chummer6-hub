#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$script_dir/_env.sh" ]]; then
  source "$script_dir/_env.sh"
fi

ROOT_DIR="$(cd "$script_dir/../.." && pwd)"
cd "$ROOT_DIR"

build_arguments=(--nologo --disable-build-servers)
case "${CHUMMER_BUILD_NO_RESTORE:-0}" in
  0) ;;
  1)
    if [[ "${CHUMMER_BUILD_SOLUTION:-0}" != "0" ]]; then
      echo "proof-mode cleanroom builds forbid the unbound solution lane." >&2
      exit 2
    fi
    build_arguments+=(
      --no-restore
      --no-incremental
      -t:Rebuild
      -p:Configuration=Debug
      -p:TargetFramework=net10.0
      -p:RuntimeIdentifier=
      -p:BuildProjectReferences=false
      -p:UseSharedCompilation=false
    )
    ;;
  *)
    echo "CHUMMER_BUILD_NO_RESTORE must be 0 or 1." >&2
    exit 2
    ;;
esac

build_if_present() {
  local project_path="$1"
  if [[ ! -f "$project_path" ]]; then
    echo "skip missing project: $project_path"
    return 0
  fi
  /usr/bin/dotnet build "$project_path" "${build_arguments[@]}"
}

build_if_present ../chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj
build_if_present ../chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj
build_if_present Chummer.Play.Contracts/Chummer.Play.Contracts.csproj
build_if_present Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj
build_if_present Chummer.Control.Contracts/Chummer.Control.Contracts.csproj
build_if_present Chummer.World.Contracts/Chummer.World.Contracts.csproj
build_if_present ../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj
build_if_present Chummer.Run.Contracts/Chummer.Run.Contracts.csproj
build_if_present ../chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj
build_if_present ../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime/Chummer.Media.Factory.Runtime.csproj

local_slice_requires_full_run_services_tree=0
for project_path in \
  "Chummer.Play.Contracts/Chummer.Play.Contracts.csproj" \
  "Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj" \
  "Chummer.Control.Contracts/Chummer.Control.Contracts.csproj" \
  "Chummer.Run.Contracts/Chummer.Run.Contracts.csproj" \
  "Chummer.World.Contracts/Chummer.World.Contracts.csproj" \
  "Chummer.Run.Identity/Chummer.Run.Identity.csproj" \
  "Chummer.Run.AI/Chummer.Run.AI.csproj"
do
  if [[ ! -f "$project_path" ]]; then
    local_slice_requires_full_run_services_tree=1
    break
  fi
done

if [[ "$local_slice_requires_full_run_services_tree" = "1" ]]; then
  echo "skip local run-services app build: repository slice does not include the full contract/service project tree"
else
  build_if_present Chummer.Run.Api/Chummer.Run.Api.csproj
  build_if_present Chummer.Run.Identity/Chummer.Run.Identity.csproj
  build_if_present Chummer.Run.AI/Chummer.Run.AI.csproj
fi

if [ "${CHUMMER_BUILD_SOLUTION:-0}" = "1" ]; then
  if ! /usr/bin/dotnet build Chummer.Run.sln "${build_arguments[@]}"; then
    echo "solution-level build unsupported in current host environment; set CHUMMER_BUILD_SOLUTION=0 to skip." >&2
  fi
fi
