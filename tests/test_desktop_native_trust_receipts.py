from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_desktop_native_trust_receipts.py"
PROOF_SCRIPT = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"
QUEUE_PROOF_LINES = [
    "    proof:",
    "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InstallLinkingController.cs",
    "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/DesktopInstallRail.cs",
    "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/Support/SupportCasePresentationService.cs",
    "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml",
    "      - /docker/chummercomplete/chummer.run-services/scripts/verify_desktop_native_trust_receipts.py",
    "      - /docker/chummercomplete/chummer.run-services/tests/test_desktop_native_trust_receipts.py",
    "      - /docker/chummercomplete/chummer.run-services/Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs",
    "      - /docker/chummercomplete/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "      - /docker/chummercomplete/chummer.run-services commit e27f24c1 tightens desktop-native continuation fallback-posture proof.",
    "      - /docker/chummercomplete/chummer.run-services commit e578a519 tightens the completed M102 proof pin.",
    "      - /docker/chummercomplete/chummer.run-services commit 9fcec2a0 fail-closes M102 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
    "      - /docker/chummercomplete/chummer.run-services commit 266d526b pins the M102 queue proof hardening commit.",
    "      - /docker/chummercomplete/chummer.run-services commit 6ea510c8 pins the M102 telemetry guard proof evidence.",
    "      - /docker/chummercomplete/chummer.run-services commit 7a825c73 pins the M102 desktop trust guard evidence.",
    "      - /docker/chummercomplete/chummer.run-services commit aff39474 pins the M102 desktop trust latest guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 38d50742 pins the M102 desktop trust proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit b9404a4c pins the M102 desktop trust latest proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit e6ae11a7 pins the M102 desktop trust guard closure.",
    "      - /docker/chummercomplete/chummer.run-services commit 4c542b50 pins the latest M102 desktop trust closure guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 02bed909 pins the M102 desktop trust closure guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 2017cdfe requires the latest M102 desktop trust proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 24432002 tightens the current M102 desktop trust proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 4afd6c3e pins the current M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit d99d080e pins the M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit b5b25e98 tightens M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit d7cb9d6e pins M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit ec81b660 pins M102 desktop trust current proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit b2d5cbfc tightens M102 generated proof hygiene.",
    "      - /docker/chummercomplete/chummer.run-services commit 5eac0f47 pins M102 desktop trust current proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 91514d42 pins M102 desktop trust proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit f7031d74 pins M102 desktop trust guard floor.",
    "      - /docker/chummercomplete/chummer.run-services commit f169b4a0 requires the current M102 desktop trust guard.",
    "      - /docker/chummercomplete/chummer.run-services commit b473e033 pins the current M102 desktop trust guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 782fa007 requires the current M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 26817b22 pins M102 desktop trust current proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 6cf10549 pins M102 desktop trust 268 proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit de9653ee pins M102 desktop trust latest proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 3760ef63 tightens M102 active-run proof marker matching so queue, registry, and generated proof evidence reject helper references regardless of casing.",
    "      - /docker/chummercomplete/chummer.run-services commit 0337eeb5 pins the M102 active-run casing proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit ad21e50f pins the M102 active-run casing proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 51c46e74 pins the M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit ed3989d9 pins the M102 desktop trust proof floor guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 653b23f0 tightens M102 desktop trust proof floor guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 1a1c5615 pins M102 desktop trust current proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit ed689925 pins M102 desktop trust latest proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 461e3709 pins M102 desktop trust current proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 171c2de0 tightens M102 blocked run-helper proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 73f1ee9a pins M102 desktop trust proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 74dff34c tightens M102 forbidden command evidence guard.",
    "      - /docker/chummercomplete/chummer.run-services commit aea02326 pins the M102 forbidden command proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 2330a11c pins the current M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 99a03a04 pins the M102 current desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 0dca4b42 pins the M102 landed proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 2c351c92 pins M102 landed proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 575daa11 pins M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit bffcad4d tightens M102 proof timestamp stability so generatedAt-only proof refreshes do not reopen the closed desktop-native trust package.",
    "      - /docker/chummercomplete/chummer.run-services commit 9454feb7 pins M102 timestamp proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit f1513793 pins M102 timestamp proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 7ddbc973 pins M102 current proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 01800bd9 pins M102 current desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit c9bbf63c tightens M102 served proof shelf route guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 2f7ed420 tightens M102 duplicate package-row proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 15c5f0e5 tightens M102 generated proof uniqueness so duplicate package or receipt rows fail closed.",
    "      - /docker/chummercomplete/chummer.run-services commit a270dcd0 tightens M102 desktop callback proof so app-local install-link callbacks cannot drift back to browser-only continuation.",
    "      - /docker/chummercomplete/chummer.run-services commit 4fa19f0c pins M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 6f468ee9 tightens M102 worker-state proof guard so run-state helper output cannot close desktop-native trust evidence.",
    "      - /docker/chummercomplete/chummer.run-services commit 4ed1f541 pins the M102 supervisor proof guard floor so future shards verify the current completed-package guard.",
    "      - /docker/chummercomplete/chummer.run-services commit f3300fd9 pins the M102 supervisor proof guard into the verifier and unit guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 06fa0634 pins the M102 local proof floor guard.",
    "      - /docker/chummercomplete/chummer.run-services commit f23b6dc4 records the M102 proof floor in the verifier.",
    "      - /docker/chummercomplete/chummer.run-services commit 7cf5461b pins the M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit cae283e9 requires the current M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit e908400b pins the M102 current desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 1870132d pins the latest M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 6b811ca2 pins the latest M102 desktop trust guard floor.",
    "      - /docker/chummercomplete/chummer.run-services commit b7107364 pins the M102 desktop trust guard floor.",
    "      - /docker/chummercomplete/chummer.run-services commit f49c64a9 pins the M102 current desktop trust guard floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 512f3569 pins the M102 current desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit ff9c3313 pins the M102 latest desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit de158f6b tightens M102 worker-context proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 8a542230 pins the M102 worker-context proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 74c3b75b pins the M102 worker-context proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 76b350fc tightens M102 materialized proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit d3b19c88 pins the M102 materialized proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 39af99da pins the M102 materialized proof floor guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 7d86f38e pins the current M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit c0c4dca1 records the M102 desktop trust proof citation.",
    "      - /docker/chummercomplete/chummer.run-services commit 42a3d5a4 pins the M102 desktop trust citation floor.",
    "      - /docker/chummercomplete/chummer.run-services commit af567e58 pins the M102 desktop trust verifier floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 2620a2f4 requires the M102 desktop trust verifier floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 5917695a pins the M102 current verifier floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 2ded9038 tightens M102 app-local callback proof so localhost and 127.0.0.1 install-link callbacks stay desktop-native.",
    "      - /docker/chummercomplete/chummer.run-services commit e7b5177b tightens M102 loopback callback proof so IPv6 app-local install-link callbacks stay desktop-native.",
    "      - /docker/chummercomplete/chummer.run-services commit d72386ee pins the M102 loopback callback proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit fee0655a tightens M102 app-local callback state proof so the desktop listener's state query survives grant callback continuation.",
    "      - /docker/chummercomplete/chummer.run-services commit 568b8358 tightens M102 app-local callback query-context proof.",
    "      - /docker/chummercomplete/chummer.run-services commit e0bcd91d pins the M102 callback query proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit aadffb5b pins the M102 callback query proof guard.",
    "      - /docker/chummercomplete/chummer.run-services commit a7a5ecea tightens M102 desktop trust callback proof.",
    "      - /docker/chummercomplete/chummer.run-services commit 4b9c6919 pins the M102 desktop trust callback proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit ea697985 tightens M102 receipt route proof so receipt routes must be served by top-level proof_routes.",
    "      - /docker/chummercomplete/chummer.run-services commit e9c87a3f tightens M102 served proof parity so the public proof shelf cannot drift from canonical published proof.",
    "      - /docker/chummercomplete/chummer.run-services commit d3c74d38 tightens M102 queue mirror proof so Fleet and design-owned successor queue rows cannot drift apart.",
    "      - /docker/chummercomplete/chummer.run-services commit 6b5679de tightens M102 support continuation filtering so reporter-level install-help cases cannot attach to the wrong claimed desktop install.",
    "      - /docker/chummercomplete/chummer.run-services commit 39c0ae8d tightens M102 app-local callback path proof so claimed desktop callbacks cannot drift to arbitrary localhost browser routes.",
    "      - /docker/chummercomplete/chummer.run-services commit 8e90aac9 pins the M102 app-local callback path proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit b27c5142 pins the M102 app-local proof floor guard.",
    "      - /docker/chummercomplete/chummer.run-services commit cd392a72 pins the M102 current proof floor guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 41d7ed57 pins the M102 current desktop trust floor.",
    "      - /docker/chummercomplete/chummer.run-services commit bd60fc5a tightens M102 active-run evidence path guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 2791f798 tightens M102 support intake installed-build truth.",
    "      - /docker/chummercomplete/chummer.run-services commit 93e5075a tightens M102 current proof floor guard.",
    "      - /docker/chummercomplete/chummer.run-services commit 894dbedd pins M102 current proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit 997337a6 pins M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer.run-services commit e24162d9 requires M102 desktop trust proof citation.",
    "      - /docker/chummercomplete/chummer.run-services commit bb8db39c tightens M102 support install matching.",
    "      - python3 scripts/verify_desktop_native_trust_receipts.py",
    "      - python3 -m unittest tests/test_desktop_native_trust_receipts.py",
    '      - dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "DesktopInstallRailTests|PublicLandingClaimRecoveryFlowTests|InstallLinkingContinuationVerification|InstallLinkingControllerBrowserCallbackTests" --no-restore',
]
REGISTRY_102_1_LINES = [
    "milestones:",
    "  - id: 102",
    "    work_tasks:",
    "      - id: 102.1",
    "        owner: chummer6-hub",
    "        status: complete",
    "        landed_commit: 160af58f",
    "        evidence:",
    "          - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InstallLinkingController.cs exposes /api/v1/install-linking/continuation for grant-bound claimed desktop installs with current release, update, rollback, and support continuation truth.",
    "          - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml and /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/Accounts/Account.cshtml make guided setup/app continuation the default and keep claim codes as recovery fallback only.",
    "          - /docker/chummercomplete/chummer.run-services/scripts/verify_desktop_native_trust_receipts.py fail-closes missing source markers and missing successor proof receipts for desktop_native_claim_and_recovery and support_followthrough:install_truth.",
    "          - /docker/chummercomplete/chummer.run-services/Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs covers app-local localhost and 127.0.0.1 install-link callbacks so claimed desktop users return to the app-local continuation listener instead of browser-only continuation.",
    "          - /docker/chummercomplete/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json carries next90-m102-hub-desktop-native-trust proof receipts for /downloads/install/avalonia-linux-x64-installer/continue.json, /api/v1/install-linking/continuation, /account/access, /account/support, and /contact.",
    "          - /docker/chummercomplete/chummer.run-services commit e27f24c1 tightens desktop-native continuation fallback-posture proof so claimed installs return the same fallback posture used by download and support recovery.",
    "          - /docker/chummercomplete/chummer.run-services commit e578a519 tightens the completed M102 proof pin so future shards verify the closed package instead of repeating it.",
    "          - /docker/chummercomplete/chummer.run-services commit 9fcec2a0 fail-closes M102 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
    "          - /docker/chummercomplete/chummer.run-services commit 266d526b pins the M102 queue proof hardening commit so stale queue proof cannot keep the package green.",
    "          - /docker/chummercomplete/chummer.run-services commit 6ea510c8 pins the M102 telemetry guard proof evidence so future shards verify the latest closed-package guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 7a825c73 pins the M102 desktop trust guard evidence into the verifier and unit guard.",
    "          - /docker/chummercomplete/chummer.run-services commit aff39474 pins the M102 desktop trust latest guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 38d50742 pins the M102 desktop trust proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit b9404a4c pins the M102 desktop trust latest proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit e6ae11a7 pins the M102 desktop trust guard closure.",
    "          - /docker/chummercomplete/chummer.run-services commit 4c542b50 pins the latest M102 desktop trust closure guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 02bed909 pins the M102 desktop trust closure guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 2017cdfe requires the latest M102 desktop trust proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 24432002 tightens the current M102 desktop trust proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 4afd6c3e pins the current M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit d99d080e pins the M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit b5b25e98 tightens M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit d7cb9d6e pins M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit ec81b660 pins M102 desktop trust current proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit b2d5cbfc tightens M102 generated proof hygiene.",
    "          - /docker/chummercomplete/chummer.run-services commit 5eac0f47 pins M102 desktop trust current proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 91514d42 pins M102 desktop trust proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit f7031d74 pins M102 desktop trust guard floor.",
    "          - /docker/chummercomplete/chummer.run-services commit f169b4a0 requires the current M102 desktop trust guard.",
    "          - /docker/chummercomplete/chummer.run-services commit b473e033 pins the current M102 desktop trust guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 782fa007 requires the current M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 26817b22 pins M102 desktop trust current proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 6cf10549 pins M102 desktop trust 268 proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit de9653ee pins M102 desktop trust latest proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 3760ef63 tightens M102 active-run proof marker matching so queue, registry, and generated proof evidence reject helper references regardless of casing.",
    "          - /docker/chummercomplete/chummer.run-services commit 0337eeb5 pins the M102 active-run casing proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit ad21e50f pins the M102 active-run casing proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 51c46e74 pins the M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit ed3989d9 pins the M102 desktop trust proof floor guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 653b23f0 tightens M102 desktop trust proof floor guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 1a1c5615 pins M102 desktop trust current proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit ed689925 pins M102 desktop trust latest proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 461e3709 pins M102 desktop trust current proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 171c2de0 tightens M102 blocked run-helper proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 73f1ee9a pins M102 desktop trust proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 74dff34c tightens M102 forbidden command evidence guard.",
    "          - /docker/chummercomplete/chummer.run-services commit aea02326 pins the M102 forbidden command proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 2330a11c pins the current M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 99a03a04 pins the M102 current desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 0dca4b42 pins the M102 landed proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 2c351c92 pins M102 landed proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 575daa11 pins M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit bffcad4d tightens M102 proof timestamp stability so generatedAt-only proof refreshes do not reopen the closed desktop-native trust package.",
    "          - /docker/chummercomplete/chummer.run-services commit 9454feb7 pins M102 timestamp proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit f1513793 pins M102 timestamp proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 7ddbc973 pins M102 current proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 01800bd9 pins M102 current desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit c9bbf63c tightens M102 served proof shelf route guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 2f7ed420 tightens M102 duplicate package-row proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 15c5f0e5 tightens M102 generated proof uniqueness so duplicate package or receipt rows fail closed.",
    "          - /docker/chummercomplete/chummer.run-services commit a270dcd0 tightens M102 desktop callback proof so app-local install-link callbacks cannot drift back to browser-only continuation.",
    "          - /docker/chummercomplete/chummer.run-services commit 4fa19f0c pins M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 6f468ee9 tightens M102 worker-state proof guard so run-state helper output cannot close desktop-native trust evidence.",
    "          - /docker/chummercomplete/chummer.run-services commit 4ed1f541 pins the M102 supervisor proof guard floor so future shards verify the current completed-package guard.",
    "          - /docker/chummercomplete/chummer.run-services commit f3300fd9 pins the M102 supervisor proof guard into the verifier and unit guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 06fa0634 pins the M102 local proof floor guard.",
    "          - /docker/chummercomplete/chummer.run-services commit f23b6dc4 records the M102 proof floor in the verifier.",
    "          - /docker/chummercomplete/chummer.run-services commit 7cf5461b pins the M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit cae283e9 requires the current M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit e908400b pins the M102 current desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 1870132d pins the latest M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 6b811ca2 pins the latest M102 desktop trust guard floor.",
    "          - /docker/chummercomplete/chummer.run-services commit b7107364 pins the M102 desktop trust guard floor.",
    "          - /docker/chummercomplete/chummer.run-services commit f49c64a9 pins the M102 current desktop trust guard floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 512f3569 pins the M102 current desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit ff9c3313 pins the M102 latest desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit de158f6b tightens M102 worker-context proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 8a542230 pins the M102 worker-context proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 74c3b75b pins the M102 worker-context proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 76b350fc tightens M102 materialized proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit d3b19c88 pins the M102 materialized proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 39af99da pins the M102 materialized proof floor guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 7d86f38e pins the current M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit c0c4dca1 records the M102 desktop trust proof citation.",
    "          - /docker/chummercomplete/chummer.run-services commit 42a3d5a4 pins the M102 desktop trust citation floor.",
    "          - /docker/chummercomplete/chummer.run-services commit af567e58 pins the M102 desktop trust verifier floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 2620a2f4 requires the M102 desktop trust verifier floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 5917695a pins the M102 current verifier floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 2ded9038 tightens M102 app-local callback proof so localhost and 127.0.0.1 install-link callbacks stay desktop-native.",
    "          - /docker/chummercomplete/chummer.run-services commit e7b5177b tightens M102 loopback callback proof so IPv6 app-local install-link callbacks stay desktop-native.",
    "          - /docker/chummercomplete/chummer.run-services commit d72386ee pins the M102 loopback callback proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit fee0655a tightens M102 app-local callback state proof so the desktop listener's state query survives grant callback continuation.",
    "          - /docker/chummercomplete/chummer.run-services commit 568b8358 tightens M102 app-local callback query-context proof.",
    "          - /docker/chummercomplete/chummer.run-services commit e0bcd91d pins the M102 callback query proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit aadffb5b pins the M102 callback query proof guard.",
    "          - /docker/chummercomplete/chummer.run-services commit a7a5ecea tightens M102 desktop trust callback proof.",
    "          - /docker/chummercomplete/chummer.run-services commit 4b9c6919 pins the M102 desktop trust callback proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit ea697985 tightens M102 receipt route proof so receipt routes must be served by top-level proof_routes.",
    "          - /docker/chummercomplete/chummer.run-services commit e9c87a3f tightens M102 served proof parity so the public proof shelf cannot drift from canonical published proof.",
    "          - /docker/chummercomplete/chummer.run-services commit d3c74d38 tightens M102 queue mirror proof so Fleet and design-owned successor queue rows cannot drift apart.",
    "          - /docker/chummercomplete/chummer.run-services commit 6b5679de tightens M102 support continuation filtering so reporter-level install-help cases cannot attach to the wrong claimed desktop install.",
    "          - /docker/chummercomplete/chummer.run-services commit 39c0ae8d tightens M102 app-local callback path proof so claimed desktop callbacks cannot drift to arbitrary localhost browser routes.",
    "          - /docker/chummercomplete/chummer.run-services commit 8e90aac9 pins the M102 app-local callback path proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit b27c5142 pins the M102 app-local proof floor guard.",
    "          - /docker/chummercomplete/chummer.run-services commit cd392a72 pins the M102 current proof floor guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 41d7ed57 pins the M102 current desktop trust floor.",
    "          - /docker/chummercomplete/chummer.run-services commit bd60fc5a tightens M102 active-run evidence path guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 2791f798 tightens M102 support intake installed-build truth.",
    "          - /docker/chummercomplete/chummer.run-services commit 93e5075a tightens M102 current proof floor guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 894dbedd pins M102 current proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit 997337a6 pins M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer.run-services commit e24162d9 requires M102 desktop trust proof citation.",
    "          - /docker/chummercomplete/chummer.run-services commit bb8db39c tightens M102 support install matching.",
    "          - python3 scripts/verify_desktop_native_trust_receipts.py and python3 -m unittest tests/test_desktop_native_trust_receipts.py exit 0.",
    '          - dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "DesktopInstallRailTests|PublicLandingClaimRecoveryFlowTests|InstallLinkingContinuationVerification|InstallLinkingControllerBrowserCallbackTests" --no-restore exits 0 for net10.0 and net10.0-windows.',
]
ABSOLUTE_REPO_PREFIX = "/docker/chummercomplete/chummer.run-services/"


def load_verifier_module():
    spec = importlib.util.spec_from_file_location("verify_desktop_native_trust_receipts", VERIFY_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load verifier module from {VERIFY_SCRIPT}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def proof_anchor_paths() -> list[Path]:
    anchors: list[Path] = []
    for value in [*QUEUE_PROOF_LINES, *REGISTRY_102_1_LINES]:
        stripped = value.strip()
        if not stripped.startswith("- "):
            continue

        proof_value = stripped[2:]
        if not proof_value.startswith(ABSOLUTE_REPO_PREFIX):
            continue

        relative = proof_value[len(ABSOLUTE_REPO_PREFIX) :].split(" ", 1)[0]
        if relative and relative not in {str(item) for item in anchors}:
            anchors.append(Path(relative))

    return anchors


class DesktopNativeTrustReceiptTests(unittest.TestCase):
    def test_verifier_passes_current_repo_and_published_proof(self) -> None:
        result = subprocess.run(
            ["python3", str(VERIFY_SCRIPT)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            0,
            result.returncode,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertIn("desktop native trust receipts verified", result.stdout)

    def test_verifier_fail_closes_missing_current_local_proof_floor(self) -> None:
        result = subprocess.run(
            ["python3", str(VERIFY_SCRIPT)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={
                **dict(os.environ),
                "CHUMMER_DESKTOP_NATIVE_TRUST_CURRENT_PROOF_FLOOR_COMMIT": "deadbeef",
            },
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "current M102 desktop-native trust proof floor does not resolve: deadbeef",
            result.stderr,
        )

    def test_verifier_default_current_floor_matches_latest_canonical_guard(self) -> None:
        verifier = load_verifier_module()

        self.assertEqual("bb8db39c", verifier._current_local_proof_floor_commit())
        self.assertEqual(
            "Tighten M102 support install matching",
            verifier.CURRENT_LOCAL_PROOF_FLOOR_SUBJECT,
        )
        self.assertIn("bb8db39c", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("e24162d9", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("997337a6", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("894dbedd", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("93e5075a", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("2791f798", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("bd60fc5a", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("41d7ed57", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("cd392a72", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertTrue(
            any("commit bb8db39c tightens M102 support install matching." in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit bb8db39c tightens M102 support install matching." in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )

    def test_materializer_publishes_m102_desktop_native_trust_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            result = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                0,
                result.returncode,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            proof = proof_path.read_text(encoding="utf-8")
            self.assertIn("next90-m102-hub-desktop-native-trust", proof)
            self.assertIn("desktop_native_claim_and_recovery", proof)
            self.assertIn("support_followthrough:install_truth", proof)
            self.assertIn("/api/v1/install-linking/continuation", proof)
            payload = json.loads(proof)
            self.assertIn("/downloads/install/avalonia-linux-x64-installer/continue.json", payload["proof_routes"])
            self.assertIn("/api/v1/install-linking/continuation", payload["proof_routes"])
            self.assertIn("/account/access", payload["proof_routes"])
            m102_package = next(
                item
                for item in payload["successor_queue_packages"]
                if item["package_id"] == "next90-m102-hub-desktop-native-trust"
            )
            self.assertEqual("complete", m102_package["status"])
            self.assertEqual("160af58f", m102_package["landed_commit"])
            self.assertEqual(
                "Unify claim, install, update, and support recovery into one desktop-native flow",
                m102_package["title"],
            )
            self.assertEqual(["Chummer.Run.Api", "scripts", "tests"], m102_package["allowed_paths"])
            self.assertEqual(
                "Claim, update, rollback, recovery, and support followthrough happen from the installer or app, not as browser ritual.",
                m102_package["exit_criterion"],
            )
            m105_package = next(
                item
                for item in payload["successor_queue_packages"]
                if item["package_id"] == "next90-m105-hub-workspace-continuity"
            )
            self.assertEqual("complete", m105_package["status"])
            self.assertEqual("4d4b3856", m105_package["landed_commit"])
            self.assertEqual(["Chummer.Run.Api", "scripts", "tests"], m105_package["allowed_paths"])
            self.assertEqual(
                ["workspace_restore:provenance", "entitlement_sync:conflict_receipts"],
                m105_package["owned_surfaces"],
            )

    def test_verifier_fail_closes_successor_queue_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            queue_path.write_text(
                "\n".join(
                    [
                        "items:",
                        "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                        "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                        "    package_id: next90-m102-hub-desktop-native-trust",
                        "    frontier_id: 2897065929",
                        "    milestone_id: 102",
                        "    wave: W6",
                        "    repo: chummer6-hub",
                        "    status: in_progress",
                        "    allowed_paths:",
                        "      - Chummer.Run.Api",
                        "    owned_surfaces:",
                        "      - desktop_native_claim_and_recovery",
                        "      - support_followthrough:install_truth",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(
                "\n".join(
                    [
                        "items:",
                        "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                        "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                        "    package_id: next90-m102-hub-desktop-native-trust",
                        "    frontier_id: 2897065929",
                        "    milestone_id: 102",
                        "    wave: W6",
                        "    repo: chummer6-hub",
                        "    status: complete",
                        "    landed_commit: 160af58f",
                        *QUEUE_PROOF_LINES,
                        "    allowed_paths:",
                        "      - Chummer.Run.Api",
                        "      - scripts",
                        "      - tests",
                        "    owned_surfaces:",
                        "      - desktop_native_claim_and_recovery",
                        "      - support_followthrough:install_truth",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("canonical successor queue staging block missing marker: status: complete", result.stderr)
            self.assertIn("canonical successor queue staging block missing marker: landed_commit: 160af58f", result.stderr)

    def test_verifier_fail_closes_design_successor_queue_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            design_queue_path.write_text(
                complete_queue.replace("landed_commit: 160af58f", "landed_commit: stale-commit") + "\n",
                encoding="utf-8",
            )
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("canonical design successor queue staging block missing marker: landed_commit: 160af58f", result.stderr)

    def test_verifier_fail_closes_successor_queue_package_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(
                complete_queue.replace(
                    "task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "task: Browser-only support fallback.",
                )
                + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "canonical successor queue staging block missing marker: "
                "task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                result.stderr,
            )

    def test_verifier_fail_closes_successor_queue_frontier_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(
                complete_queue.replace("    frontier_id: 2897065929\n", "") + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("canonical successor queue staging block missing marker: frontier_id: 2897065929", result.stderr)

    def test_verifier_fail_closes_duplicate_successor_queue_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(
                complete_queue
                + "\n"
                + complete_queue.replace("items:\n", "").replace("    landed_commit: 160af58f", "    landed_commit: duplicate")
                + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "canonical successor queue staging has 2 rows anchored by: "
                "package_id: next90-m102-hub-desktop-native-trust",
                result.stderr,
            )

    def test_verifier_fail_closes_duplicate_successor_registry_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES)
                + "\n"
                + "\n".join(REGISTRY_102_1_LINES).replace("        landed_commit: 160af58f", "        landed_commit: duplicate")
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("canonical successor registry has 2 rows anchored by: id: 102.1", result.stderr)

    def test_verifier_fail_closes_successor_queue_scope_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(
                complete_queue.replace("      - tests\n", "") + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("canonical successor queue staging block has wrong allowed_paths", result.stderr)

    def test_verifier_fail_closes_successor_queue_proof_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(
                complete_queue.replace(
                    "      - python3 scripts/verify_desktop_native_trust_receipts.py\n",
                    "",
                )
                + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("canonical successor queue staging block has wrong proof", result.stderr)

    def test_verifier_fail_closes_successor_queue_mirror_block_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            design_queue_path.write_text(
                complete_queue.replace(
                    "    landed_commit: 160af58f\n",
                    "    landed_commit: 160af58f\n"
                    "    mirror_only_note: stale queue mirror evidence must not close this package\n",
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "Fleet successor queue staging block for next90-m102-hub-desktop-native-trust "
                "drifts from the design-owned successor queue source",
                result.stderr,
            )

    def test_verifier_fail_closes_successor_registry_evidence_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(
                    line
                    for line in REGISTRY_102_1_LINES
                    if "python3 scripts/verify_desktop_native_trust_receipts.py and python3 -m unittest" not in line
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("canonical successor registry block has wrong evidence", result.stderr)

    def test_verifier_fail_closes_successor_queue_active_run_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(
                complete_queue.replace(
                    "      - python3 -m unittest tests/test_desktop_native_trust_receipts.py\n",
                    "      - python3 -m unittest tests/test_desktop_native_trust_receipts.py\n"
                    "      - /VAR/LIB/CODEX-FLEET/chummer_design_supervisor/shard-1/active_run_handoff.generated.md\n"
                    "      - active-run helper commands run_ooda_design_supervisor_until_quiet.py output\n"
                    "      - supervisor status query output with status_query_supported=false, polling_disabled=true, and polling disabled\n"
                    "      - task-local telemetry first_commands and frontier_briefs with remaining milestones, remaining queue items, critical path, successor frontier detail, and shard runtime handoff\n",
                )
                + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: /var/lib/codex-fleet",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: ACTIVE_RUN_HANDOFF",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: active-run helper command",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: active-run helper commands",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: run_ooda_design_supervisor_until_quiet",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: supervisor status",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: status query",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: status_query_supported",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: polling_disabled",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: polling disabled",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: task-local telemetry",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: first_commands",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: frontier_briefs",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: remaining milestones",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: remaining queue items",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: critical path",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: successor frontier detail",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: shard runtime handoff",
                result.stderr,
            )

    def test_verifier_fail_closes_active_run_evidence_path_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_dir = Path(temp_root) / "TASK_LOCAL_TELEMETRY.generated.json"
            queue_dir.mkdir()
            queue_path = queue_dir / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "configured successor queue staging path has forbidden active-run proof marker: "
                "TASK_LOCAL_TELEMETRY",
                result.stderr,
            )

    def test_verifier_fail_closes_successor_registry_active_run_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(
                    [
                        *REGISTRY_102_1_LINES,
                        "          - Task_Local_Telemetry.generated.json Active-Run Helper Commands output from ooda_design_supervisor.py and the operator/OODA loop",
                        "          - Supervisor status query output with status_query_supported=false, polling_disabled=true, and polling disabled",
                        "          - Task-local telemetry first_commands and frontier_briefs with remaining milestones, remaining queue items, critical path, successor frontier detail, and shard runtime handoff",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: TASK_LOCAL_TELEMETRY",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: active-run helper",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: active-run helper command",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: active-run helper commands",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: ooda_design_supervisor.py",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: operator/OODA loop",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: supervisor status",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: status query",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: status_query_supported",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: polling_disabled",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: polling disabled",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: task-local telemetry",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: first_commands",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: frontier_briefs",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: remaining milestones",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: remaining queue items",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: critical path",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: successor frontier detail",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: shard runtime handoff",
                result.stderr,
            )

    def test_verifier_fail_closes_generated_proof_package_scope_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            m102_package = next(
                item
                for item in proof["successor_queue_packages"]
                if item["package_id"] == "next90-m102-hub-desktop-native-trust"
            )
            m102_package["allowed_paths"] = ["Chummer.Run.Api", "scripts"]
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("proof package has wrong allowed_paths", result.stderr)
            self.assertIn(
                "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from scripts/materialize_hub_local_release_proof.py",
                result.stderr,
            )

    def test_verifier_fail_closes_duplicate_generated_m102_package_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            m102_package = next(
                item
                for item in proof["successor_queue_packages"]
                if item["package_id"] == "next90-m102-hub-desktop-native-trust"
            )
            proof["successor_queue_packages"].append(dict(m102_package))
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "published proof file has 2 successor_queue_packages entries for "
                "next90-m102-hub-desktop-native-trust",
                result.stderr,
            )
            self.assertIn(
                "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from scripts/materialize_hub_local_release_proof.py",
                result.stderr,
            )

    def test_verifier_fail_closes_materialized_proof_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            m102_receipt = next(
                item
                for item in proof["proof_receipts"]
                if item["receipt_id"] == "desktop_native_claim_and_recovery"
            )
            m102_receipt["summary"] = "stale local receipt text"
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from scripts/materialize_hub_local_release_proof.py",
                result.stderr,
            )

    def test_verifier_fail_closes_served_proof_drift_from_published_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            served_proof_path = Path(temp_root) / "served" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            served_proof_path.parent.mkdir()
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            served_proof = dict(proof)
            served_proof["base_url"] = "https://stale-proof-shelf.example"
            served_proof_path.write_text(json.dumps(served_proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                    "CHUMMER_HUB_SERVED_RELEASE_PROOF_PATH": str(served_proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "served HUB_LOCAL_RELEASE_PROOF.generated.json drifts from "
                "published HUB_LOCAL_RELEASE_PROOF.generated.json",
                result.stderr,
            )

    def test_verifier_fail_closes_duplicate_generated_m102_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            m102_receipt = next(
                item
                for item in proof["proof_receipts"]
                if item["receipt_id"] == "support_followthrough:install_truth"
            )
            proof["proof_receipts"].append(dict(m102_receipt))
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "published proof file has 2 proof_receipts entries for support_followthrough:install_truth",
                result.stderr,
            )
            self.assertIn(
                "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from scripts/materialize_hub_local_release_proof.py",
                result.stderr,
            )

    def test_verifier_allows_generated_at_timestamp_only_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["generatedAt"] = "2099-01-01T00:00:00Z"
            proof["generated_at"] = "2099-01-01T00:00:00Z"
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertEqual(
                0,
                result.returncode,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertIn("desktop native trust receipts verified", result.stdout)

    def test_verifier_fail_closes_weakened_generated_package_exit_criterion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            m102_package = next(
                item
                for item in proof["successor_queue_packages"]
                if item["package_id"] == "next90-m102-hub-desktop-native-trust"
            )
            m102_package["exit_criterion"] = "Claim codes are still acceptable as the main continuation path."
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("proof package has wrong exit_criterion", result.stderr)
            self.assertIn(
                "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from scripts/materialize_hub_local_release_proof.py",
                result.stderr,
            )

    def test_verifier_fail_closes_weakened_desktop_native_receipt_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            m102_receipt = next(
                item
                for item in proof["proof_receipts"]
                if item["receipt_id"] == "desktop_native_claim_and_recovery"
            )
            m102_receipt["summary"] = "Claim continuation may start in a browser if that is more convenient."
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("desktop_native_claim_and_recovery has wrong summary", result.stderr)
            self.assertIn(
                "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from scripts/materialize_hub_local_release_proof.py",
                result.stderr,
            )

    def test_verifier_fail_closes_generated_proof_active_run_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            m102_receipt = next(
                item
                for item in proof["proof_receipts"]
                if item["receipt_id"] == "support_followthrough:install_truth"
            )
            m102_receipt["evidence"] = [
                "/VAR/LIB/CODEX-FLEET/chummer_design_supervisor/shard-1/active_run_handoff.generated.md",
                "Operator Telemetry helper output",
                "Supervisor status query output with status_query_supported=false, polling_disabled=true, and polling disabled",
                "Task-local telemetry first_commands and frontier_briefs with remaining milestones, remaining queue items, critical path, successor frontier detail, and shard runtime handoff",
            ]
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[0]: /var/lib/codex-fleet",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[0]: ACTIVE_RUN_HANDOFF",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[1]: operator telemetry",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[2]: supervisor status",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[2]: status query",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[2]: status_query_supported",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[2]: polling_disabled",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[2]: polling disabled",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[3]: task-local telemetry",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[3]: first_commands",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[3]: frontier_briefs",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[3]: remaining milestones",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[3]: remaining queue items",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[3]: critical path",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[3]: successor frontier detail",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[3]: shard runtime handoff",
                result.stderr,
            )

    def test_verifier_fail_closes_served_proof_route_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            served_proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(served_proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(served_proof_path.read_text(encoding="utf-8"))
            proof["proof_routes"] = [
                route
                for route in proof["proof_routes"]
                if route != "/api/v1/install-linking/continuation"
            ]
            served_proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_SERVED_RELEASE_PROOF_PATH": str(served_proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "served release proof file proof_routes missing M102 route: "
                "/api/v1/install-linking/continuation",
                result.stderr,
            )

    def test_verifier_fail_closes_missing_canonical_proof_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            anchor_root = Path(temp_root)
            missing_anchor = Path("tests/test_desktop_native_trust_receipts.py")
            for anchor in proof_anchor_paths():
                if anchor == missing_anchor:
                    continue

                path = anchor_root / anchor
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("placeholder\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_RUN_SERVICES_PROOF_ANCHOR_ROOT": str(anchor_root),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "canonical proof anchor does not resolve: "
                "/docker/chummercomplete/chummer.run-services/tests/test_desktop_native_trust_receipts.py",
                result.stderr,
            )

    def test_verifier_fail_closes_non_resolving_proof_commit(self) -> None:
        result = subprocess.run(
            ["python3", str(VERIFY_SCRIPT)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={
                **dict(os.environ),
                "CHUMMER_DESKTOP_NATIVE_TRUST_EXTRA_REQUIRED_COMMITS": "0000000000000000000000000000000000000000",
            },
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "required M102 desktop-native trust proof commit does not resolve: "
            "0000000000000000000000000000000000000000",
            result.stderr,
        )

    def test_verifier_requires_desktop_native_hardening_commits(self) -> None:
        verifier = load_verifier_module()

        self.assertEqual(
            [
                "160af58f",
                "e27f24c1",
                "0ea22419",
                "b4d761a2",
                "e75c4a97",
                "e578a519",
                "9fcec2a0",
                "266d526b",
                "6ea510c8",
                "7a825c73",
                "aff39474",
                "38d50742",
                "b9404a4c",
                "e6ae11a7",
                "4c542b50",
                "02bed909",
                "2017cdfe",
                "24432002",
                "4afd6c3e",
                "d99d080e",
                "b5b25e98",
                "d7cb9d6e",
                "ec81b660",
                "b2d5cbfc",
                "5eac0f47",
                "91514d42",
                "f7031d74",
                "f169b4a0",
                "b473e033",
                "782fa007",
                "26817b22",
                "6cf10549",
                "de9653ee",
                "3760ef63",
                "0337eeb5",
                "ad21e50f",
                "51c46e74",
                "ed3989d9",
                "653b23f0",
                "1a1c5615",
                "ed689925",
                "461e3709",
                "171c2de0",
                "73f1ee9a",
                "74dff34c",
                "aea02326",
                "2330a11c",
                "99a03a04",
                "0dca4b42",
                "2c351c92",
                "575daa11",
                "bffcad4d",
                "9454feb7",
                "f1513793",
                "7ddbc973",
                "01800bd9",
                "c9bbf63c",
                "2f7ed420",
                "15c5f0e5",
                "a270dcd0",
                "4fa19f0c",
                "6f468ee9",
                "4ed1f541",
                "f3300fd9",
                "06fa0634",
                "f23b6dc4",
                "7cf5461b",
                "cae283e9",
                "e908400b",
                "1870132d",
                "6b811ca2",
                "b7107364",
                "f49c64a9",
                "512f3569",
                "ff9c3313",
                "de158f6b",
                "8a542230",
                "74c3b75b",
                "76b350fc",
                "d3b19c88",
                "39af99da",
                "a4d16005",
                "1893a245",
                "7d86f38e",
                "c0c4dca1",
                "42a3d5a4",
                "af567e58",
                "2620a2f4",
                "5917695a",
                "2ded9038",
                "e7b5177b",
                "d72386ee",
                "fee0655a",
                "568b8358",
                "e0bcd91d",
                "aadffb5b",
                "a7a5ecea",
                "4b9c6919",
                "ea697985",
                "e9c87a3f",
                "d3c74d38",
                "6b5679de",
                "39c0ae8d",
                "8e90aac9",
                "b27c5142",
                "bc52177b",
                "cd392a72",
                "41d7ed57",
                "bd60fc5a",
                "2791f798",
                "93e5075a",
                "894dbedd",
                "997337a6",
                "e24162d9",
                "bb8db39c",
            ],
            verifier._required_resolving_commits(),
        )

    def test_verifier_fail_closes_canonical_commit_floor_drift(self) -> None:
        verifier = load_verifier_module()
        original_queue_proof = list(verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        original_registry_evidence = list(verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        original_required_commits = list(verifier.REQUIRED_RESOLVING_COMMITS)

        try:
            verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"] = [
                value
                for value in original_queue_proof
                if "commit 73f1ee9a pins M102 desktop trust proof guard" not in value
            ]
            errors: list[str] = []
            verifier._verify_canonical_commit_floor_consistency(errors)

            self.assertTrue(
                any("M102 canonical queue and registry proof commit floors differ" in error for error in errors),
                errors,
            )

            verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"] = list(original_queue_proof)
            verifier.REQUIRED_RESOLVING_COMMITS = [
                commit
                for commit in original_required_commits
                if commit != "73f1ee9a"
            ]
            errors = []
            verifier._verify_canonical_commit_floor_consistency(errors)

            self.assertIn(
                "M102 canonical proof cites commit not enforced by resolver: 73f1ee9a",
                errors,
            )
        finally:
            verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"] = original_queue_proof
            verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"] = original_registry_evidence
            verifier.REQUIRED_RESOLVING_COMMITS = original_required_commits

    def test_verifier_fail_closes_duplicate_canonical_commit_citations(self) -> None:
        verifier = load_verifier_module()
        original_queue_proof = list(verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        original_registry_evidence = list(verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])

        try:
            verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"] = original_queue_proof + [
                "/docker/chummercomplete/chummer.run-services commit bb8db39c duplicate proof row."
            ]
            verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"] = original_registry_evidence + [
                "/docker/chummercomplete/chummer.run-services commit bb8db39c duplicate proof row."
            ]
            errors: list[str] = []
            verifier._verify_canonical_commit_floor_consistency(errors)

            self.assertIn(
                "M102 canonical queue proof has duplicate commit citations: ['bb8db39c']",
                errors,
            )
            self.assertIn(
                "M102 canonical registry proof has duplicate commit citations: ['bb8db39c']",
                errors,
            )
        finally:
            verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"] = original_queue_proof
            verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"] = original_registry_evidence

    def test_verifier_fail_closes_current_proof_floor_missing_from_canonical_evidence(self) -> None:
        verifier = load_verifier_module()
        original_queue_proof = list(verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        original_registry_evidence = list(verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        original_required_commits = list(verifier.REQUIRED_RESOLVING_COMMITS)

        try:
            verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"] = [
                value
                for value in original_queue_proof
                if f"commit {verifier.CURRENT_LOCAL_PROOF_FLOOR_COMMIT} " not in value
            ]
            verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"] = [
                value
                for value in original_registry_evidence
                if f"commit {verifier.CURRENT_LOCAL_PROOF_FLOOR_COMMIT} " not in value
            ]
            errors: list[str] = []
            verifier._verify_current_local_proof_floor(errors, REPO_ROOT)

            self.assertIn(
                "current M102 desktop-native trust proof floor is missing from canonical queue proof: "
                f"{verifier.CURRENT_LOCAL_PROOF_FLOOR_COMMIT}",
                errors,
            )
            self.assertIn(
                "current M102 desktop-native trust proof floor is missing from canonical registry evidence: "
                f"{verifier.CURRENT_LOCAL_PROOF_FLOOR_COMMIT}",
                errors,
            )

            verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"] = list(original_queue_proof)
            verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"] = list(original_registry_evidence)
            verifier.REQUIRED_RESOLVING_COMMITS = [
                commit
                for commit in original_required_commits
                if commit != verifier.CURRENT_LOCAL_PROOF_FLOOR_COMMIT
            ]
            errors = []
            verifier._verify_current_local_proof_floor(errors, REPO_ROOT)

            self.assertIn(
                "current M102 desktop-native trust proof floor is not enforced by resolver: "
                f"{verifier.CURRENT_LOCAL_PROOF_FLOOR_COMMIT}",
                errors,
            )
        finally:
            verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"] = original_queue_proof
            verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"] = original_registry_evidence
            verifier.REQUIRED_RESOLVING_COMMITS = original_required_commits

    def test_verifier_fail_closes_missing_standard_verify_wiring(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            verify_sh = repo_root / "scripts/ai/verify.sh"
            verify_sh.write_text("#!/usr/bin/env bash\nset -euo pipefail\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "scripts/ai/verify.sh missing marker: python3 scripts/verify_desktop_native_trust_receipts.py",
                errors,
            )

    def test_verifier_fail_closes_account_continuation_copy_drift(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == Path("Chummer.Run.Api/Views/Accounts/Account.cshtml"):
                    markers = [
                        marker
                        for marker in markers
                        if marker != "instead of starting a fresh browser ritual."
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Views/Accounts/Account.cshtml missing marker: "
                "instead of starting a fresh browser ritual.",
                errors,
            )

    def test_verifier_fail_closes_support_case_install_receipt_drift(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == Path("Chummer.Run.Api/Controllers/InstallLinkingController.cs"):
                    markers = [
                        marker
                        for marker in markers
                        if marker != "InstalledBuildReceiptId: receipt?.ReceiptId"
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Controllers/InstallLinkingController.cs missing marker: "
                "InstalledBuildReceiptId: receipt?.ReceiptId",
                errors,
            )

    def test_verifier_fail_closes_desktop_callback_target_drift(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == Path("Chummer.Run.Api/Controllers/InstallLinkingController.cs"):
                    markers = [
                        marker
                        for marker in markers
                        if marker != "string.Equals(parsed.Host, \"install-link\", StringComparison.OrdinalIgnoreCase)"
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Controllers/InstallLinkingController.cs missing marker: "
                "string.Equals(parsed.Host, \"install-link\", StringComparison.OrdinalIgnoreCase)",
                errors,
            )

    def test_verifier_fail_closes_app_local_callback_state_drift(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == Path("Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs"):
                    markers = [
                        marker
                        for marker in markers
                        if marker != 'Assert.Contains("state=desktop", redirect.Url, StringComparison.Ordinal);'
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs missing marker: "
                'Assert.Contains("state=desktop", redirect.Url, StringComparison.Ordinal);',
                errors,
            )

    def test_verifier_fail_closes_app_local_callback_query_context_drift(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == Path("Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs"):
                    markers = [
                        marker
                        for marker in markers
                        if marker != 'Assert.Contains("nonce=callback-proof", redirect.Url, StringComparison.Ordinal);'
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs missing marker: "
                'Assert.Contains("nonce=callback-proof", redirect.Url, StringComparison.Ordinal);',
                errors,
            )

    def test_verifier_fail_closes_app_local_callback_path_drift(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == Path("Chummer.Run.Api/Controllers/InstallLinkingController.cs"):
                    markers = [
                        marker
                        for marker in markers
                        if marker != "IsAppLocalInstallLinkCallbackPath(parsed.AbsolutePath)"
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Controllers/InstallLinkingController.cs missing marker: "
                "IsAppLocalInstallLinkCallbackPath(parsed.AbsolutePath)",
                errors,
            )

    def test_verifier_fail_closes_browser_only_local_callback_acceptance_drift(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == Path("Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs"):
                    markers = [
                        marker
                        for marker in markers
                        if marker != "http://127.0.0.1:47761/browser-only/claim?state=desktop"
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs missing marker: "
                "http://127.0.0.1:47761/browser-only/claim?state=desktop",
                errors,
            )

    def test_verifier_fail_closes_top_level_m102_proof_route_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["proof_routes"] = [
                item
                for item in proof["proof_routes"]
                if item != "/api/v1/install-linking/continuation"
            ]
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("proof_routes missing M102 route: /api/v1/install-linking/continuation", result.stderr)

    def test_verifier_fail_closes_receipt_route_outside_top_level_proof_shelf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            receipt = next(
                item
                for item in proof["proof_receipts"]
                if item["receipt_id"] == "desktop_native_claim_and_recovery"
            )
            receipt["routes"].append("/account/access/browser-only-claim")
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                    "CHUMMER_HUB_SERVED_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "published proof file desktop_native_claim_and_recovery route is not listed "
                "in top-level proof_routes: /account/access/browser-only-claim",
                result.stderr,
            )

    def test_verifier_fail_closes_duplicate_m102_proof_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["proof_routes"].append("/API/V1/INSTALL-LINKING/CONTINUATION")
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "published proof file proof_routes has duplicate entries: "
                "/API/V1/INSTALL-LINKING/CONTINUATION",
                result.stderr,
            )

    def test_verifier_fail_closes_top_level_m102_journey_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["journeys_passed"] = [
                item
                for item in proof["journeys_passed"]
                if item != "install_claim_restore_continue"
            ]
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("journeys_passed missing M102 journey: install_claim_restore_continue", result.stderr)

    def test_verifier_fail_closes_duplicate_m102_journey_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["journeys_passed"].append("Install_Claim_Restore_Continue")
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "published proof file journeys_passed has duplicate entries: "
                "Install_Claim_Restore_Continue",
                result.stderr,
            )

    def test_verifier_fail_closes_duplicate_m102_receipt_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            receipt = next(
                item
                for item in proof["proof_receipts"]
                if item["receipt_id"] == "support_followthrough:install_truth"
            )
            receipt["routes"].append("/ACCOUNT/SUPPORT")
            receipt["surfaces"].append("Support_Followthrough:Install_Truth")
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "published proof file support_followthrough:install_truth surfaces "
                "has duplicate entries: Support_Followthrough:Install_Truth",
                result.stderr,
            )
            self.assertIn(
                "published proof file support_followthrough:install_truth routes "
                "has duplicate entries: /ACCOUNT/SUPPORT",
                result.stderr,
            )

    def test_verifier_fail_closes_expanded_m102_receipt_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            receipt = next(
                item
                for item in proof["proof_receipts"]
                if item["receipt_id"] == "desktop_native_claim_and_recovery"
            )
            receipt["routes"].append("/account/support")
            receipt["surfaces"].append("support_case_install_readiness")
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                    "CHUMMER_HUB_SERVED_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "published proof file desktop_native_claim_and_recovery has wrong surfaces: ",
                result.stderr,
            )
            self.assertIn(
                "published proof file desktop_native_claim_and_recovery has wrong routes: ",
                result.stderr,
            )


if __name__ == "__main__":
    unittest.main()
