#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

dotnet build Chummer.Play.Contracts/Chummer.Play.Contracts.csproj --nologo
dotnet build Chummer.Media.Contracts/Chummer.Media.Contracts.csproj --nologo
dotnet build Chummer.Run.Contracts/Chummer.Run.Contracts.csproj --nologo
dotnet build Chummer.Run.Api/Chummer.Run.Api.csproj --nologo
dotnet build Chummer.Run.Identity/Chummer.Run.Identity.csproj --nologo
dotnet build Chummer.Run.Registry/Chummer.Run.Registry.csproj --nologo
dotnet build Chummer.Run.AI/Chummer.Run.AI.csproj --nologo

if [ "${CHUMMER_BUILD_SOLUTION:-0}" = "1" ]; then
  if ! dotnet build Chummer.Run.sln --nologo; then
    echo "solution-level build unsupported in current host environment; set CHUMMER_BUILD_SOLUTION=0 to skip." >&2
  fi
fi
