#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${1:-https://chummer.run}"
ACCOUNT_PROOF_IDENTITY_TOKEN="${CHUMMER_E2E_IDENTITY_TOKEN:-}"
ACCOUNT_PROOF_LOCAL_IDENTITY_TOKEN="${CHUMMER_E2E_LOCAL_IDENTITY_TOKEN:-}"

if [[ -z "$ACCOUNT_PROOF_IDENTITY_TOKEN" && -z "$ACCOUNT_PROOF_LOCAL_IDENTITY_TOKEN" ]]; then
  echo "[release-dress-rehearsal] signed-in account proof requires CHUMMER_E2E_IDENTITY_TOKEN or CHUMMER_E2E_LOCAL_IDENTITY_TOKEN" >&2
  exit 2
fi
if [[ -n "$ACCOUNT_PROOF_IDENTITY_TOKEN" && -n "$ACCOUNT_PROOF_LOCAL_IDENTITY_TOKEN" ]]; then
  echo "[release-dress-rehearsal] set only one hosted or local account proof identity token" >&2
  exit 2
fi

# Keep the credential out of unrelated rehearsal subprocesses; expose it only to Playwright below.
unset CHUMMER_E2E_IDENTITY_TOKEN CHUMMER_E2E_LOCAL_IDENTITY_TOKEN

cd "$REPO_ROOT"

python3 scripts/run_gold_janitor.py --final --include-live "$BASE_URL"
python3 scripts/public_asset_quality_gate.py --base-url "$BASE_URL"
python3 scripts/ledger_stats_privacy_gate.py --base-url "$BASE_URL"
python3 scripts/verify_public_copy_leak_gate.py --base-url "$BASE_URL"
python3 scripts/materialize_design_quality_gate.py
python3 scripts/materialize_operator_release_dashboard.py --release-ready-self-check
dotnet test Chummer.Tests/Chummer.Tests.csproj --filter ParticipantNotification
python3 -m pytest -q tests/test_ea_operator_notification_delivery.py
BASE_URL="$BASE_URL" \
CHUMMER_REQUIRE_SIGNED_IN_ACCOUNT_PROOF=1 \
CHUMMER_E2E_IDENTITY_TOKEN="$ACCOUNT_PROOF_IDENTITY_TOKEN" \
CHUMMER_E2E_LOCAL_IDENTITY_TOKEN="$ACCOUNT_PROOF_LOCAL_IDENTITY_TOKEN" \
npx playwright test \
  tests/public/account-access.spec.ts \
  tests/public/frontdoor-mobile-launch.spec.ts \
  account-participation-dashboard.spec.ts \
  homepage-flagship-redesign.spec.ts \
  black-ledger-stats.spec.ts \
  karma-forge-pipeline.spec.ts \
  public-cta-hierarchy.spec.ts \
  package-browser.spec.ts \
  tests/public/mobile-pwa-public.spec.ts \
  public-responsive-gold.spec.ts \
  tests/public/ui-frame-integrity.spec.ts

python3 scripts/ui_layout_exit_gate.py
