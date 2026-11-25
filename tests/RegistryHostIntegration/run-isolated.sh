#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 2 ]]; then
  echo 'Usage: run-isolated.sh /absolute/path/to/dotnet /absolute/path/to/RegistryHostIntegration.dll' >&2
  exit 2
fi
sdk=$(realpath "$1")
verifier=$(realpath "$2")
[[ -x "$sdk" && -f "$verifier" ]]
root=$(mktemp -d /tmp/chummer-registry-host.XXXXXXXX)
trap 'rm -rf -- "$root"' EXIT
mkdir -p "$root/home" "$root/tmp"
# A fresh test process has no inherited service credentials, configuration,
# account cache, user-secrets directory or proxy settings. No network listener.
env -i PATH=/usr/bin:/bin HOME="$root/home" TMPDIR="$root/tmp" \
  DOTNET_ROOT="$(dirname "$sdk")" DOTNET_ENVIRONMENT=RegistryHostTest \
  ASPNETCORE_ENVIRONMENT=RegistryHostTest DOTNET_CLI_TELEMETRY_OPTOUT=1 \
  DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1 CHUMMER_REGISTRY_HOST_TEST_ROOT="$root" \
  "$sdk" "$verifier"
