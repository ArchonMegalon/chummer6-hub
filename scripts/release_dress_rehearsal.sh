#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${1:-https://chummer.run}"

cd "$REPO_ROOT"

python3 scripts/run_gold_janitor.py --final --include-live "$BASE_URL"
python3 scripts/public_asset_quality_gate.py --base-url "$BASE_URL"
python3 scripts/ledger_stats_privacy_gate.py --base-url "$BASE_URL"
python3 scripts/verify_public_copy_leak_gate.py --base-url "$BASE_URL"
python3 scripts/materialize_design_quality_gate.py
python3 scripts/materialize_operator_release_dashboard.py
dotnet test Chummer.Tests/Chummer.Tests.csproj --filter ParticipantNotification
python3 -m pytest -q tests/test_ea_operator_notification_delivery.py
npx playwright test \
  account-participation-dashboard.spec.ts \
  homepage-flagship-redesign.spec.ts \
  black-ledger-stats.spec.ts \
  karma-forge-pipeline.spec.ts \
  public-cta-hierarchy.spec.ts \
  package-browser.spec.ts \
  mobile-pwa-public.spec.ts \
  public-responsive-gold.spec.ts \
  tests/public/ui-frame-integrity.spec.ts

python3 scripts/ui_layout_exit_gate.py
