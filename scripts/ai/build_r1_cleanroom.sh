#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$script_dir/_env.sh" ]]; then
  source "$script_dir/_env.sh"
fi

ROOT_DIR="$(cd "$script_dir/../.." && pwd)"
cd "$ROOT_DIR"

build_if_present() {
  local project_path="$1"
  if [[ ! -f "$project_path" ]]; then
    echo "skip missing project: $project_path"
    return 0
  fi
  dotnet build "$project_path" --nologo --disable-build-servers
}

build_if_present ../chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj
build_if_present ../chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj
build_if_present ../chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj
build_if_present ../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj
build_if_present ../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime/Chummer.Media.Factory.Runtime.csproj

if [[ -f Chummer.Play.Contracts/Chummer.Play.Contracts.csproj ]]; then
  dotnet build Chummer.Play.Contracts/Chummer.Play.Contracts.csproj --nologo --disable-build-servers
else
  echo "skip missing project: Chummer.Play.Contracts/Chummer.Play.Contracts.csproj"
fi

if [[ -f Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj ]]; then
  dotnet build Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj --nologo --disable-build-servers
else
  echo "skip missing project: Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj"
fi

if [[ -f Chummer.Control.Contracts/Chummer.Control.Contracts.csproj ]]; then
  dotnet build Chummer.Control.Contracts/Chummer.Control.Contracts.csproj --nologo --disable-build-servers
else
  echo "skip missing project: Chummer.Control.Contracts/Chummer.Control.Contracts.csproj"
fi

if [[ -f Chummer.Run.Contracts/Chummer.Run.Contracts.csproj ]]; then
  dotnet build Chummer.Run.Contracts/Chummer.Run.Contracts.csproj --nologo --disable-build-servers
else
  echo "skip missing project: Chummer.Run.Contracts/Chummer.Run.Contracts.csproj"
fi

local_slice_requires_full_run_services_tree=0
for project_path in \
  "Chummer.Play.Contracts/Chummer.Play.Contracts.csproj" \
  "Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj" \
  "Chummer.Control.Contracts/Chummer.Control.Contracts.csproj" \
  "Chummer.Run.Contracts/Chummer.Run.Contracts.csproj" \
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
  dotnet build Chummer.Run.Api/Chummer.Run.Api.csproj --nologo --disable-build-servers
  dotnet build Chummer.Run.Identity/Chummer.Run.Identity.csproj --nologo --disable-build-servers
  dotnet build Chummer.Run.AI/Chummer.Run.AI.csproj --nologo --disable-build-servers
fi

if [ "${CHUMMER_BUILD_SOLUTION:-0}" = "1" ]; then
  if ! dotnet build Chummer.Run.sln --nologo --disable-build-servers; then
    echo "solution-level build unsupported in current host environment; set CHUMMER_BUILD_SOLUTION=0 to skip." >&2
  fi
fi
