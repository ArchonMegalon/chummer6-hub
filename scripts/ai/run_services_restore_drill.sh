#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="${ROOT_DIR}/.tmp/run-services-restore-drill"
mkdir -p "$TMP_DIR"

scripts/ai/build_r1_cleanroom.sh >/dev/null

SDK_VERSION="$(dotnet --version)"
DOTNET_ROOT="$(dirname "$(readlink -f "$(command -v dotnet)")")"
CSC_DLL="${DOTNET_ROOT}/sdk/${SDK_VERSION}/Roslyn/bincore/csc.dll"
NETCORE_REF_DIR="$(find "${DOTNET_ROOT}/packs/Microsoft.NETCore.App.Ref" -path '*/ref/net10.0' -type d | sort | tail -n 1)"
ASPNET_REF_DIR="$(find "${DOTNET_ROOT}/packs/Microsoft.AspNetCore.App.Ref" -path '*/ref/net10.0' -type d | sort | tail -n 1)"
NETCORE_RUNTIME_VERSION="$(dotnet --list-runtimes | awk '/Microsoft.NETCore.App 10\./ { print $2; exit }')"
ASPNET_RUNTIME_VERSION="$(dotnet --list-runtimes | awk '/Microsoft.AspNetCore.App 10\./ { print $2; exit }')"
OUT_DLL="${TMP_DIR}/RunServicesRestoreDrill.dll"
RSP_FILE="${TMP_DIR}/RunServicesRestoreDrill.rsp"
PROGRAM_FILE="${TMP_DIR}/RestoreDrillProgram.cs"

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
cp Chummer.Run.AI/bin/Debug/net10.0/Chummer.Run.AI.dll "$TMP_DIR/"
cp Chummer.Run.Contracts/bin/Debug/net10.0/Chummer.Run.Contracts.dll "$TMP_DIR/"

cat > "$PROGRAM_FILE" <<'EOF'
using RunServicesVerification;

await StateStoreBackupVerification.RunAsync();
Console.WriteLine("run-services restore drill passed");
EOF

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
  echo "${ROOT_DIR}/tests/RunServicesVerification/GlobalUsings.cs"
  echo "${ROOT_DIR}/tests/RunServicesVerification/VerificationAssert.cs"
  echo "${ROOT_DIR}/tests/RunServicesVerification/StateStoreBackupVerification.cs"
  echo "${PROGRAM_FILE}"
} > "$RSP_FILE"

cat > "${TMP_DIR}/RunServicesRestoreDrill.runtimeconfig.json" <<EOF
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
