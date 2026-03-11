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

if ! grep -En '<HintPath>\.\.\\Chummer\.Play\.Contracts\\bin\\\$\(Configuration\)\\net8\.0\\Chummer\.Play\.Contracts\.dll</HintPath>' \
  Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
  Chummer.Run.AI/Chummer.Run.AI.csproj >/dev/null; then
  echo "Chummer.Play.Contracts consumers must point at the built canonical contract assembly." >&2
  exit 1
fi

if ! grep -En '<HintPath>\.\.\\Chummer\.Media\.Contracts\\bin\\\$\(Configuration\)\\net8\.0\\Chummer\.Media\.Contracts\.dll</HintPath>' \
  Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
  Chummer.Run.AI/Chummer.Run.AI.csproj >/dev/null; then
  echo "Chummer.Media.Contracts consumers must point at the built canonical contract assembly." >&2
  exit 1
fi

if [ -f Chummer.Run.Api/Controllers/PublicationsController.cs ] || [ -f Chummer.Run.Api/Services/PublicationWorkflowService.cs ]; then
  echo "Publication ownership must stay in Chummer.Run.Registry, not Chummer.Run.Api." >&2
  exit 1
fi

if [ ! -f Chummer.Run.Registry/Controllers/PublicationsController.cs ] || [ ! -f Chummer.Run.Registry/Services/PublicationWorkflowService.cs ]; then
  echo "Chummer.Run.Registry must host publication controller/workflow for hub-registry boundary readiness." >&2
  exit 1
fi

if ! grep -En '<ProjectReference Include="\.\.\\Chummer\.Run\.Contracts\\Chummer\.Run\.Contracts\.csproj" />' \
  Chummer.Run.Registry/Chummer.Run.Registry.csproj >/dev/null; then
  echo "Chummer.Run.Registry must depend on Chummer.Run.Contracts for canonical registry/publication contracts." >&2
  exit 1
fi

if grep -En '<ProjectReference Include="\.\.\\Chummer\.Run\.(AI|Api|Identity)\\' \
  Chummer.Run.Registry/Chummer.Run.Registry.csproj >/dev/null; then
  echo "Chummer.Run.Registry must not take dependencies on run-services orchestrator projects." >&2
  exit 1
fi

scripts/ai/build_r1_cleanroom.sh >/dev/null

SDK_VERSION="$(dotnet --version)"
DOTNET_ROOT="$(dirname "$(readlink -f "$(command -v dotnet)")")"
CSC_DLL="${DOTNET_ROOT}/sdk/${SDK_VERSION}/Roslyn/bincore/csc.dll"
NETCORE_REF_DIR="$(find "${DOTNET_ROOT}/packs/Microsoft.NETCore.App.Ref" -path '*/ref/net8.0' -type d | sort | tail -n 1)"
ASPNET_REF_DIR="$(find "${DOTNET_ROOT}/packs/Microsoft.AspNetCore.App.Ref" -path '*/ref/net8.0' -type d | sort | tail -n 1)"
NETCORE_RUNTIME_VERSION="$(dotnet --list-runtimes | awk '/Microsoft.NETCore.App 8\./ { print $2; exit }')"
ASPNET_RUNTIME_VERSION="$(dotnet --list-runtimes | awk '/Microsoft.AspNetCore.App 8\./ { print $2; exit }')"
OUT_DLL="${TMP_DIR}/RunServicesVerification.dll"
RSP_FILE="${TMP_DIR}/RunServicesVerification.rsp"

if [[ ! -f "$CSC_DLL" || -z "$NETCORE_REF_DIR" || -z "$ASPNET_REF_DIR" || -z "$NETCORE_RUNTIME_VERSION" || -z "$ASPNET_RUNTIME_VERSION" ]]; then
  echo "unable to resolve installed .NET 8 SDK/reference/runtime locations" >&2
  exit 1
fi

cp Chummer.Play.Contracts/bin/Debug/net8.0/Chummer.Play.Contracts.dll "$TMP_DIR/"
cp Chummer.Media.Contracts/bin/Debug/net8.0/Chummer.Media.Contracts.dll "$TMP_DIR/"
cp Chummer.Run.Api/bin/Debug/net8.0/Chummer.Run.Api.dll "$TMP_DIR/"
cp Chummer.Run.Identity/bin/Debug/net8.0/Chummer.Run.Identity.dll "$TMP_DIR/"
cp Chummer.Run.Registry/bin/Debug/net8.0/Chummer.Run.Registry.dll "$TMP_DIR/"
cp Chummer.Run.AI/bin/Debug/net8.0/Chummer.Run.AI.dll "$TMP_DIR/"
cp Chummer.Run.Contracts/bin/Debug/net8.0/Chummer.Run.Contracts.dll "$TMP_DIR/"

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
  find "${ROOT_DIR}/tests/RunServicesVerification" -maxdepth 1 -name '*.cs' | sort
} > "$RSP_FILE"

cat > "${TMP_DIR}/RunServicesVerification.runtimeconfig.json" <<EOF
{
  "runtimeOptions": {
    "tfm": "net8.0",
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
