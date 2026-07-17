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

TEST_BIN="Chummer.Tests/bin/Debug/net10.0"

resolve_artifact() {
  local label="$1"
  shift
  local candidate
  for candidate in "$@"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  echo "missing artifact for ${label}" >&2
  return 1
}

copy_artifact() {
  local label="$1"
  local output_name="$2"
  shift 2
  local source_path
  source_path="$(resolve_artifact "$label" "$@")" || return 1
  cp "$source_path" "${TMP_DIR}/${output_name}"
}

if [[ "${CHUMMER_SKIP_CLEANROOM_BUILD:-0}" != "1" ]]; then
  "$script_dir/build_r1_cleanroom.sh" >/dev/null
fi

resolve_artifact "Chummer.Play.Contracts" \
  "Chummer.Play.Contracts/bin/Debug/net10.0/Chummer.Play.Contracts.dll" \
  "${TEST_BIN}/Chummer.Play.Contracts.dll" >/dev/null || { echo "skip run-services smoke: repository slice does not include required local run-services artifacts"; exit 0; }
resolve_artifact "Chummer.Campaign.Contracts" \
  "Chummer.Campaign.Contracts/bin/Debug/net10.0/Chummer.Campaign.Contracts.dll" \
  "${TEST_BIN}/Chummer.Campaign.Contracts.dll" >/dev/null || { echo "skip run-services smoke: repository slice does not include required local run-services artifacts"; exit 0; }
resolve_artifact "Chummer.Control.Contracts" \
  "Chummer.Control.Contracts/bin/Debug/net10.0/Chummer.Control.Contracts.dll" \
  "${TEST_BIN}/Chummer.Control.Contracts.dll" >/dev/null || { echo "skip run-services smoke: repository slice does not include required local run-services artifacts"; exit 0; }
resolve_artifact "Chummer.Run.Api" \
  "Chummer.Run.Api/bin/Debug/net10.0/Chummer.Run.Api.dll" \
  "${TEST_BIN}/Chummer.Run.Api.dll" >/dev/null || { echo "skip run-services smoke: repository slice does not include required local run-services artifacts"; exit 0; }
resolve_artifact "Chummer.Run.Identity" \
  "Chummer.Run.Identity/bin/Debug/net10.0/Chummer.Run.Identity.dll" \
  "${TEST_BIN}/Chummer.Run.Identity.dll" >/dev/null || { echo "skip run-services smoke: repository slice does not include required local run-services artifacts"; exit 0; }
resolve_artifact "Chummer.Run.AI" \
  "Chummer.Run.AI/bin/Debug/net10.0/Chummer.Run.AI.dll" \
  "${TEST_BIN}/Chummer.Run.AI.dll" >/dev/null || { echo "skip run-services smoke: repository slice does not include required local run-services artifacts"; exit 0; }
resolve_artifact "Chummer.Run.Contracts" \
  "Chummer.Run.Contracts/bin/Debug/net10.0/Chummer.Run.Contracts.dll" \
  "${TEST_BIN}/Chummer.Run.Contracts.dll" >/dev/null || { echo "skip run-services smoke: repository slice does not include required local run-services artifacts"; exit 0; }

SDK_VERSION="$(dotnet --version)"
DOTNET_ROOT="$(dirname "$(readlink -f "$(command -v dotnet)")")"
if [[ ! -d "${DOTNET_ROOT}/packs" || ! -d "${DOTNET_ROOT}/sdk/${SDK_VERSION}" ]]; then
  DOTNET_BASE_PATH="$(dotnet --info | awk -F': *' '/Base Path:/{print $2; exit}')"
  if [[ -n "$DOTNET_BASE_PATH" ]]; then
    DOTNET_ROOT="$(dirname "$(dirname "${DOTNET_BASE_PATH%/}")")"
  fi
fi
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

copy_artifact "Chummer.Play.Contracts" "Chummer.Play.Contracts.dll" \
  "Chummer.Play.Contracts/bin/Debug/net10.0/Chummer.Play.Contracts.dll" \
  "${TEST_BIN}/Chummer.Play.Contracts.dll"
copy_artifact "Chummer.Campaign.Contracts" "Chummer.Campaign.Contracts.dll" \
  "Chummer.Campaign.Contracts/bin/Debug/net10.0/Chummer.Campaign.Contracts.dll" \
  "${TEST_BIN}/Chummer.Campaign.Contracts.dll"
copy_artifact "Chummer.Control.Contracts" "Chummer.Control.Contracts.dll" \
  "Chummer.Control.Contracts/bin/Debug/net10.0/Chummer.Control.Contracts.dll" \
  "${TEST_BIN}/Chummer.Control.Contracts.dll"
copy_artifact "Chummer.Engine.Contracts" "Chummer.Engine.Contracts.dll" \
  "../chummer-core-engine/Chummer.Contracts/bin/Debug/net10.0/Chummer.Engine.Contracts.dll" \
  "${TEST_BIN}/Chummer.Engine.Contracts.dll"
copy_artifact "Chummer.Hub.Registry.Contracts" "Chummer.Hub.Registry.Contracts.dll" \
  "../chummer-hub-registry/Chummer.Hub.Registry.Contracts/bin/Debug/net10.0/Chummer.Hub.Registry.Contracts.dll" \
  "${TEST_BIN}/Chummer.Hub.Registry.Contracts.dll"
copy_artifact "Chummer.Run.Registry" "Chummer.Run.Registry.dll" \
  "../chummer-hub-registry/Chummer.Run.Registry/bin/Debug/net10.0/Chummer.Run.Registry.dll" \
  "${TEST_BIN}/Chummer.Run.Registry.dll"
copy_artifact "Chummer.Media.Contracts" "Chummer.Media.Contracts.dll" \
  "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/bin/Debug/net10.0/Chummer.Media.Contracts.dll" \
  "${TEST_BIN}/Chummer.Media.Contracts.dll"
copy_artifact "Chummer.Media.Factory.Runtime" "Chummer.Media.Factory.Runtime.dll" \
  "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime/bin/Debug/net10.0/Chummer.Media.Factory.Runtime.dll" \
  "${TEST_BIN}/Chummer.Media.Factory.Runtime.dll"
copy_artifact "Chummer.Run.Api" "Chummer.Run.Api.dll" \
  "Chummer.Run.Api/bin/Debug/net10.0/Chummer.Run.Api.dll" \
  "${TEST_BIN}/Chummer.Run.Api.dll"
copy_artifact "YamlDotNet" "YamlDotNet.dll" \
  "Chummer.Run.Api/bin/Debug/net10.0/YamlDotNet.dll" \
  "${TEST_BIN}/YamlDotNet.dll"
copy_artifact "Chummer.Run.Identity" "Chummer.Run.Identity.dll" \
  "Chummer.Run.Identity/bin/Debug/net10.0/Chummer.Run.Identity.dll" \
  "${TEST_BIN}/Chummer.Run.Identity.dll"
copy_artifact "Chummer.Run.AI" "Chummer.Run.AI.dll" \
  "Chummer.Run.AI/bin/Debug/net10.0/Chummer.Run.AI.dll" \
  "${TEST_BIN}/Chummer.Run.AI.dll"
copy_artifact "Chummer.Run.Contracts" "Chummer.Run.Contracts.dll" \
  "Chummer.Run.Contracts/bin/Debug/net10.0/Chummer.Run.Contracts.dll" \
  "${TEST_BIN}/Chummer.Run.Contracts.dll"

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
