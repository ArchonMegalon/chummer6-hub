#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$script_dir/_env.sh" ]]; then
  source "$script_dir/_env.sh"
fi

ROOT_DIR="$(cd "$script_dir/../.." && pwd)"
cd "$ROOT_DIR"

export CHUMMER_VERIFY_RELEASE_PROOF_MAX_AGE_SECONDS="${CHUMMER_VERIFY_RELEASE_PROOF_MAX_AGE_SECONDS:-315360000}"

TMP_ROOT="${ROOT_DIR}/.tmp"
if ! mkdir -p "$TMP_ROOT" 2>/dev/null || [[ ! -w "$TMP_ROOT" ]]; then
  TMP_ROOT="${TMPDIR:-/tmp}"
fi
TMP_DIR="$(mktemp -d "${TMP_ROOT}/run-services-smoke.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

"$script_dir/build_r1_cleanroom.sh" >/dev/null

for required_artifact in \
  "Chummer.Play.Contracts/bin/Debug/net10.0/Chummer.Play.Contracts.dll" \
  "Chummer.Campaign.Contracts/bin/Debug/net10.0/Chummer.Campaign.Contracts.dll" \
  "Chummer.Control.Contracts/bin/Debug/net10.0/Chummer.Control.Contracts.dll" \
  "Chummer.Run.Api/bin/Debug/net10.0/Chummer.Run.Api.dll" \
  "Chummer.Run.Identity/bin/Debug/net10.0/Chummer.Run.Identity.dll" \
  "Chummer.Run.AI/bin/Debug/net10.0/Chummer.Run.AI.dll" \
  "Chummer.Run.Contracts/bin/Debug/net10.0/Chummer.Run.Contracts.dll"
do
  if [[ ! -f "$required_artifact" ]]; then
    echo "skip run-services smoke: repository slice does not include required local run-services artifacts"
    exit 0
  fi
done

SDK_VERSION="$(dotnet --version)"
DOTNET_ROOT="$(dirname "$(readlink -f "$(command -v dotnet)")")"
CSC_DLL="${DOTNET_ROOT}/sdk/${SDK_VERSION}/Roslyn/bincore/csc.dll"
NETCORE_REF_DIR="$(find "${DOTNET_ROOT}/packs/Microsoft.NETCore.App.Ref" -path '*/ref/net10.0' -type d | sort | tail -n 1)"
ASPNET_REF_DIR="$(find "${DOTNET_ROOT}/packs/Microsoft.AspNetCore.App.Ref" -path '*/ref/net10.0' -type d | sort | tail -n 1)"
NETCORE_RUNTIME_VERSION="$(dotnet --list-runtimes | awk '/Microsoft.NETCore.App 10\./ { print $2; exit }')"
ASPNET_RUNTIME_VERSION="$(dotnet --list-runtimes | awk '/Microsoft.AspNetCore.App 10\./ { print $2; exit }')"
OUT_DLL="${TMP_DIR}/RunServicesSmoke.dll"
RSP_FILE="${TMP_DIR}/RunServicesSmoke.rsp"

if [[ ! -f "$CSC_DLL" || -z "$NETCORE_REF_DIR" || -z "$ASPNET_REF_DIR" || -z "$NETCORE_RUNTIME_VERSION" || -z "$ASPNET_RUNTIME_VERSION" ]]; then
  echo "unable to resolve installed .NET 10 SDK/reference/runtime locations" >&2
  exit 1
fi

cp Chummer.Play.Contracts/bin/Debug/net10.0/Chummer.Play.Contracts.dll "$TMP_DIR/"
cp Chummer.Campaign.Contracts/bin/Debug/net10.0/Chummer.Campaign.Contracts.dll "$TMP_DIR/"
cp Chummer.Control.Contracts/bin/Debug/net10.0/Chummer.Control.Contracts.dll "$TMP_DIR/"
cp ../chummer-core-engine/Chummer.Contracts/bin/Debug/net10.0/Chummer.Engine.Contracts.dll "$TMP_DIR/"
cp ../chummer-hub-registry/Chummer.Hub.Registry.Contracts/bin/Debug/net10.0/Chummer.Hub.Registry.Contracts.dll "$TMP_DIR/"
cp ../chummer-hub-registry/Chummer.Run.Registry/bin/Debug/net10.0/Chummer.Run.Registry.dll "$TMP_DIR/"
cp ../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/bin/Debug/net10.0/Chummer.Media.Contracts.dll "$TMP_DIR/"
cp ../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime/bin/Debug/net10.0/Chummer.Media.Factory.Runtime.dll "$TMP_DIR/"
cp Chummer.Run.Api/bin/Debug/net10.0/Chummer.Run.Api.dll "$TMP_DIR/"
cp Chummer.Run.Api/bin/Debug/net10.0/YamlDotNet.dll "$TMP_DIR/"
cp Chummer.Run.Identity/bin/Debug/net10.0/Chummer.Run.Identity.dll "$TMP_DIR/"
cp Chummer.Run.AI/bin/Debug/net10.0/Chummer.Run.AI.dll "$TMP_DIR/"
cp Chummer.Run.Contracts/bin/Debug/net10.0/Chummer.Run.Contracts.dll "$TMP_DIR/"

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
  for dll in "$TMP_DIR"/Chummer*.dll; do
    echo "-r:${dll}"
  done
  echo "-r:${TMP_DIR}/YamlDotNet.dll"
  echo "${ROOT_DIR}/../chummer-hub-registry/Chummer.Run.Registry/GlobalUsings.RegistryContracts.cs"
  echo "${ROOT_DIR}/tests/RunServicesSmoke/Program.cs"
} > "$RSP_FILE"

cat > "${TMP_DIR}/RunServicesSmoke.runtimeconfig.json" <<EOF
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
