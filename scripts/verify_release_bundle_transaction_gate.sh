#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd "$script_dir/.." && pwd)"
framework="${CHUMMER_RELEASE_BUNDLE_TRANSACTION_GATE_FRAMEWORK:-net10.0}"

dotnet test "$root_dir/Chummer.Tests/Chummer.Tests.csproj" \
  --framework "$framework" \
  --no-restore \
  --nologo \
  -p:UseSharedCompilation=false \
  --filter 'FullyQualifiedName~ReleaseBundlePromotionServiceTests' \
  --logger 'console;verbosity=minimal'

echo "release_bundle_transaction_gate:pass"
