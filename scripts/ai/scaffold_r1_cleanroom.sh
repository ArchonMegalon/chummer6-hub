#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"
export DOTNET_CLI_HOME="/tmp/.dotnet-cli"
export NUGET_PACKAGES="/tmp/.nuget/packages"
mkdir -p "$DOTNET_CLI_HOME" "$NUGET_PACKAGES"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

SLN_NAME="Chummer.Run"
SLN_FILE="$SLN_NAME.sln"

rm -f "$SLN_FILE"
dotnet new sln -n "$SLN_NAME"

create_project_if_missing() {
  local template="$1"
  local name="$2"
  shift 2
  if [ ! -d "$name" ]; then
    dotnet new "$template" -n "$name" -o "$name" "$@"
  fi
}

create_project_if_missing classlib Chummer.Run.Contracts
create_project_if_missing webapi Chummer.Run.Api --use-controllers --no-openapi
create_project_if_missing webapi Chummer.Run.Identity --use-controllers --no-openapi
create_project_if_missing webapi Chummer.Run.Registry --use-controllers --no-openapi
create_project_if_missing webapi Chummer.Run.AI --use-controllers --no-openapi

dotnet sln "$SLN_FILE" add \
  Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
  Chummer.Run.Api/Chummer.Run.Api.csproj \
  Chummer.Run.Identity/Chummer.Run.Identity.csproj \
  Chummer.Run.Registry/Chummer.Run.Registry.csproj \
  Chummer.Run.AI/Chummer.Run.AI.csproj

add_reference_if_missing() {
  local project="$1"
  local reference="$2"
  if ! dotnet list "$project" reference | grep -F "$reference" >/dev/null; then
    dotnet add "$project" reference "$reference"
  fi
}

add_reference_if_missing Chummer.Run.Api/Chummer.Run.Api.csproj Chummer.Run.Contracts/Chummer.Run.Contracts.csproj
add_reference_if_missing Chummer.Run.Identity/Chummer.Run.Identity.csproj Chummer.Run.Contracts/Chummer.Run.Contracts.csproj
add_reference_if_missing Chummer.Run.Registry/Chummer.Run.Registry.csproj Chummer.Run.Contracts/Chummer.Run.Contracts.csproj
add_reference_if_missing Chummer.Run.AI/Chummer.Run.AI.csproj Chummer.Run.Contracts/Chummer.Run.Contracts.csproj
