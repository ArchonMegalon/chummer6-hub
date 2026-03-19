#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="${ROOT_DIR}/.tmp/run-services-verification"
mkdir -p "$TMP_DIR"

if [ ! -f Chummer.Play.Contracts/Chummer.Play.Contracts.csproj ]; then
  echo "Chummer.Play.Contracts project is missing." >&2
  exit 1
fi

for retired_contract in \
  Chummer.Run.Contracts/HubRegistryContracts.cs \
  Chummer.Run.Contracts/RegistryContracts.cs \
  Chummer.Run.Contracts/PublicationContracts.cs; do
  if [ -e "$retired_contract" ]; then
    echo "retired local registry/publication contract shadow should not exist: $retired_contract" >&2
    exit 1
  fi
done

if ! grep -En '<HintPath>\.\.\\Chummer\.Play\.Contracts\\bin\\\$\(Configuration\)\\net10\.0\\Chummer\.Play\.Contracts\.dll</HintPath>' \
  Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
  Chummer.Run.AI/Chummer.Run.AI.csproj >/dev/null; then
  echo "Chummer.Play.Contracts consumers must point at the built canonical contract assembly." >&2
  exit 1
fi

if ! grep -En '<HintPath>\.\.\\\.\.\\\.\.\\fleet\\repos\\chummer-media-factory\\src\\Chummer\.Media\.Contracts\\bin\\\$\(Configuration\)\\net10\.0\\Chummer\.Media\.Contracts\.dll</HintPath>' \
  Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
  Chummer.Run.AI/Chummer.Run.AI.csproj >/dev/null; then
  echo "Chummer.Media.Contracts consumers must point at the owner-repo canonical contract assembly." >&2
  exit 1
fi

if ! grep -En '<HintPath>\.\.\\\.\.\\\.\.\\fleet\\repos\\chummer-media-factory\\src\\Chummer\.Media\.Factory\.Runtime\\bin\\\$\(Configuration\)\\net10\.0\\Chummer\.Media\.Factory\.Runtime\.dll</HintPath>' \
  Chummer.Run.AI/Chummer.Run.AI.csproj >/dev/null; then
  echo "Chummer.Run.AI must consume media execution through the owner-repo runtime assembly." >&2
  exit 1
fi

if ! grep -En '<HintPath>\.\.\\\.\.\\chummer-core-engine\\Chummer\.Contracts\\bin\\\$\(Configuration\)\\net10\.0\\Chummer\.Engine\.Contracts\.dll</HintPath>' \
  Chummer.Run.Contracts/Chummer.Run.Contracts.csproj >/dev/null; then
  echo "Chummer.Run.Contracts must consume the owner-repo Chummer.Engine.Contracts assembly for hosted compatibility DTOs." >&2
  exit 1
fi

if [ -d Chummer.Run.Registry ]; then
  echo "Chummer.Run.Registry must not stay source-owned inside chummer6-hub." >&2
  exit 1
fi

if [ -f Chummer.Run.Api/Controllers/PublicationsController.cs ] || [ -f Chummer.Run.Api/Services/PublicationWorkflowService.cs ]; then
  echo "Publication ownership must stay in Chummer.Run.Registry, not Chummer.Run.Api." >&2
  exit 1
fi

if [ ! -f ../chummer-hub-registry/Chummer.Run.Registry/Controllers/PublicationsController.cs ] || [ ! -f ../chummer-hub-registry/Chummer.Run.Registry/Services/PublicationWorkflowService.cs ]; then
  echo "Hub-registry must host publication controller/workflow for boundary readiness." >&2
  exit 1
fi

if ! grep -En '<HintPath>\.\.\\Chummer\.Hub\.Registry\.Contracts\\bin\\\$\(Configuration\)\\net10\.0\\Chummer\.Hub\.Registry\.Contracts\.dll</HintPath>' \
  ../chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj >/dev/null; then
  echo "Hub-registry runtime must consume the owner-repo contract assembly." >&2
  exit 1
fi

if grep -En '<ProjectReference Include="\.\.\\Chummer\.Run\.Contracts\\Chummer\.Run\.Contracts\.csproj" />' \
  ../chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj >/dev/null; then
  echo "Hub-registry runtime must not source-own registry/publication contracts through local Chummer.Run.Contracts." >&2
  exit 1
fi

for retired_media_service in \
  Chummer.Run.AI/Services/Assets/AssetLifecycleService.cs \
  Chummer.Run.AI/Services/Assets/MediaRenderJobService.cs; do
  if [ -e "$retired_media_service" ]; then
    echo "retired local media execution service should not exist: $retired_media_service" >&2
    exit 1
  fi
done

scripts/ai/build_r1_cleanroom.sh >/dev/null

SDK_VERSION="$(dotnet --version)"
DOTNET_ROOT="$(dirname "$(readlink -f "$(command -v dotnet)")")"
CSC_DLL="${DOTNET_ROOT}/sdk/${SDK_VERSION}/Roslyn/bincore/csc.dll"
NETCORE_REF_DIR="$(find "${DOTNET_ROOT}/packs/Microsoft.NETCore.App.Ref" -path '*/ref/net10.0' -type d | sort | tail -n 1)"
ASPNET_REF_DIR="$(find "${DOTNET_ROOT}/packs/Microsoft.AspNetCore.App.Ref" -path '*/ref/net10.0' -type d | sort | tail -n 1)"
NETCORE_RUNTIME_VERSION="$(dotnet --list-runtimes | awk '/Microsoft.NETCore.App 10\./ { print $2; exit }')"
ASPNET_RUNTIME_VERSION="$(dotnet --list-runtimes | awk '/Microsoft.AspNetCore.App 10\./ { print $2; exit }')"
OUT_DLL="${TMP_DIR}/RunServicesVerification.dll"
RSP_FILE="${TMP_DIR}/RunServicesVerification.rsp"

if [[ ! -f "$CSC_DLL" || -z "$NETCORE_REF_DIR" || -z "$ASPNET_REF_DIR" || -z "$NETCORE_RUNTIME_VERSION" || -z "$ASPNET_RUNTIME_VERSION" ]]; then
  echo "unable to resolve installed .NET 10 SDK/reference/runtime locations" >&2
  exit 1
fi

cp Chummer.Play.Contracts/bin/Debug/net10.0/Chummer.Play.Contracts.dll "$TMP_DIR/"
cp ../chummer-core-engine/Chummer.Contracts/bin/Debug/net10.0/Chummer.Engine.Contracts.dll "$TMP_DIR/"
cp ../chummer-hub-registry/Chummer.Hub.Registry.Contracts/bin/Debug/net10.0/Chummer.Hub.Registry.Contracts.dll "$TMP_DIR/"
cp ../chummer-hub-registry/Chummer.Run.Registry/bin/Debug/net10.0/Chummer.Run.Registry.dll "$TMP_DIR/"
cp ../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/bin/Debug/net10.0/Chummer.Media.Contracts.dll "$TMP_DIR/"
cp ../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime/bin/Debug/net10.0/Chummer.Media.Factory.Runtime.dll "$TMP_DIR/"
cp Chummer.Run.Api/bin/Debug/net10.0/Chummer.Run.Api.dll "$TMP_DIR/"
cp Chummer.Run.Identity/bin/Debug/net10.0/Chummer.Run.Identity.dll "$TMP_DIR/"
cp Chummer.Run.AI/bin/Debug/net10.0/Chummer.Run.AI.dll "$TMP_DIR/"
cp Chummer.Run.Contracts/bin/Debug/net10.0/Chummer.Run.Contracts.dll "$TMP_DIR/"

{
  echo "-nologo"
  echo "-langversion:preview"
  echo "-nullable:enable"
  echo "-target:exe"
  echo "-out:${OUT_DLL}"
  echo "-nowarn:612,618"
  for dll in "$NETCORE_REF_DIR"/*.dll; do
    echo "-r:${dll}"
  done
  for dll in "$ASPNET_REF_DIR"/*.dll; do
    echo "-r:${dll}"
  done
  for dll in "$TMP_DIR"/Chummer*.dll; do
    echo "-r:${dll}"
  done
  echo "${ROOT_DIR}/../chummer-hub-registry/Chummer.Run.Registry/GlobalUsings.RegistryContracts.cs"
  find "${ROOT_DIR}/tests/RunServicesVerification" -maxdepth 1 -name '*.cs' | sort
} > "$RSP_FILE"

cat > "${TMP_DIR}/RunServicesVerification.runtimeconfig.json" <<EOF
{
  "runtimeOptions": {
    "tfm": "net10.0",
    "frameworks": [
      {
        "name": "Microsoft.NETCore.App",
        "version": "${NETCORE_RUNTIME_VERSION}"
      },
      {
        "name": "Microsoft.AspNetCore.App",
        "version": "${ASPNET_RUNTIME_VERSION}"
      }
    ]
  }
}
EOF

dotnet "$CSC_DLL" @"$RSP_FILE"
dotnet "$OUT_DLL"
