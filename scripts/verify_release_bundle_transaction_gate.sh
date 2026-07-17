#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd -- "$script_dir/.." && pwd)"
framework="${CHUMMER_RELEASE_BUNDLE_TRANSACTION_GATE_FRAMEWORK:-net10.0}"
transaction_filter='FullyQualifiedName~Chummer.Tests.ReleaseBundlePromotionServiceTests|FullyQualifiedName~Chummer.Tests.ReleaseBundleUploadSessionServiceTests|FullyQualifiedName~Chummer.Tests.InternalReleaseBundlesControllerTests|FullyQualifiedName~Chummer.Tests.ReleaseUploadRequestGateMiddlewareTests'
trx_verifier="${CHUMMER_RELEASE_BUNDLE_TRANSACTION_TRX_VERIFIER:-$script_dir/verify_release_bundle_transaction_trx.py}"
results_dir="$(mktemp -d "${TMPDIR:-/tmp}/chummer-release-bundle-transaction.XXXXXX")"
cleanup() {
  rm -rf -- "$results_dir"
}
trap cleanup EXIT

dotnet test "$root_dir/Chummer.Tests/Chummer.Tests.csproj" \
  --framework "$framework" \
  --no-restore \
  --nologo \
  -p:UseSharedCompilation=false \
  --filter "$transaction_filter" \
  --logger 'trx;LogFileName=release-bundle-transaction.trx' \
  --results-directory "$results_dir"

/usr/bin/python3 -I \
  "$trx_verifier" \
  "$results_dir/release-bundle-transaction.trx"

printf '%s\n' 'release_bundle_transaction_gate:pass'
