from __future__ import annotations

import base64
import json
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_desktop_native_trust_receipts.py"
PROOF_SCRIPT = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"
QUEUE_PROOF_LINES = [
    "    proof:",
    "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InstallLinkingController.cs",
    "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/DesktopInstallRail.cs",
    "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Support/SupportCasePresentationService.cs",
    "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml",
    "      - /docker/chummercomplete/chummer6-hub/scripts/verify_desktop_native_trust_receipts.py",
    "      - /docker/chummercomplete/chummer6-hub/tests/test_desktop_native_trust_receipts.py",
    "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs",
    "      - /docker/chummercomplete/chummer6-hub/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "      - /docker/chummercomplete/chummer6-hub commit e27f24c1 tightens desktop-native continuation fallback-posture proof.",
    "      - /docker/chummercomplete/chummer6-hub commit e578a519 tightens the completed M102 proof pin.",
    "      - /docker/chummercomplete/chummer6-hub commit 9fcec2a0 fail-closes M102 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
    "      - /docker/chummercomplete/chummer6-hub commit 266d526b pins the M102 queue proof hardening commit.",
    "      - /docker/chummercomplete/chummer6-hub commit 6ea510c8 pins the M102 telemetry guard proof evidence.",
    "      - /docker/chummercomplete/chummer6-hub commit 7a825c73 pins the M102 desktop trust guard evidence.",
    "      - /docker/chummercomplete/chummer6-hub commit aff39474 pins the M102 desktop trust latest guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 38d50742 pins the M102 desktop trust proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit b9404a4c pins the M102 desktop trust latest proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit e6ae11a7 pins the M102 desktop trust guard closure.",
    "      - /docker/chummercomplete/chummer6-hub commit 4c542b50 pins the latest M102 desktop trust closure guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 02bed909 pins the M102 desktop trust closure guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 2017cdfe requires the latest M102 desktop trust proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 24432002 tightens the current M102 desktop trust proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 4afd6c3e pins the current M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit d99d080e pins the M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit b5b25e98 tightens M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit d7cb9d6e pins M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit ec81b660 pins M102 desktop trust current proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit b2d5cbfc tightens M102 generated proof hygiene.",
    "      - /docker/chummercomplete/chummer6-hub commit 5eac0f47 pins M102 desktop trust current proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 91514d42 pins M102 desktop trust proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit f7031d74 pins M102 desktop trust guard floor.",
    "      - /docker/chummercomplete/chummer6-hub commit f169b4a0 requires the current M102 desktop trust guard.",
    "      - /docker/chummercomplete/chummer6-hub commit b473e033 pins the current M102 desktop trust guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 782fa007 requires the current M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 26817b22 pins M102 desktop trust current proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 6cf10549 pins M102 desktop trust 268 proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit de9653ee pins M102 desktop trust latest proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 3760ef63 tightens M102 active-run proof marker matching so queue, registry, and generated proof evidence reject helper references regardless of casing.",
    "      - /docker/chummercomplete/chummer6-hub commit 0337eeb5 pins the M102 active-run casing proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit ad21e50f pins the M102 active-run casing proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 51c46e74 pins the M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit ed3989d9 pins the M102 desktop trust proof floor guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 653b23f0 tightens M102 desktop trust proof floor guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 1a1c5615 pins M102 desktop trust current proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit ed689925 pins M102 desktop trust latest proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 461e3709 pins M102 desktop trust current proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 171c2de0 tightens M102 blocked run-helper proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 73f1ee9a pins M102 desktop trust proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 74dff34c tightens M102 forbidden command evidence guard.",
    "      - /docker/chummercomplete/chummer6-hub commit aea02326 pins the M102 forbidden command proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 2330a11c pins the current M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 99a03a04 pins the M102 current desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 0dca4b42 pins the M102 landed proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 2c351c92 pins M102 landed proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 575daa11 pins M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit bffcad4d tightens M102 proof timestamp stability so generatedAt-only proof refreshes do not reopen the closed desktop-native trust package.",
    "      - /docker/chummercomplete/chummer6-hub commit 9454feb7 pins M102 timestamp proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit f1513793 pins M102 timestamp proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 7ddbc973 pins M102 current proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 01800bd9 pins M102 current desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit c9bbf63c tightens M102 served proof shelf route guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 2f7ed420 tightens M102 duplicate package-row proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 15c5f0e5 tightens M102 generated proof uniqueness so duplicate package or receipt rows fail closed.",
    "      - /docker/chummercomplete/chummer6-hub commit a270dcd0 tightens M102 desktop callback proof so app-local install-link callbacks cannot drift back to browser-only continuation.",
    "      - /docker/chummercomplete/chummer6-hub commit 4fa19f0c pins M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 6f468ee9 tightens M102 worker-state proof guard so run-state helper output cannot close desktop-native trust evidence.",
    "      - /docker/chummercomplete/chummer6-hub commit 4ed1f541 pins the M102 supervisor proof guard floor so future shards verify the current completed-package guard.",
    "      - /docker/chummercomplete/chummer6-hub commit f3300fd9 pins the M102 supervisor proof guard into the verifier and unit guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 06fa0634 pins the M102 local proof floor guard.",
    "      - /docker/chummercomplete/chummer6-hub commit f23b6dc4 records the M102 proof floor in the verifier.",
    "      - /docker/chummercomplete/chummer6-hub commit 7cf5461b pins the M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit cae283e9 requires the current M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit e908400b pins the M102 current desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 1870132d pins the latest M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 6b811ca2 pins the latest M102 desktop trust guard floor.",
    "      - /docker/chummercomplete/chummer6-hub commit b7107364 pins the M102 desktop trust guard floor.",
    "      - /docker/chummercomplete/chummer6-hub commit f49c64a9 pins the M102 current desktop trust guard floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 512f3569 pins the M102 current desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit ff9c3313 pins the M102 latest desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit de158f6b tightens M102 worker-context proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 8a542230 pins the M102 worker-context proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 74c3b75b pins the M102 worker-context proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 76b350fc tightens M102 materialized proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit d3b19c88 pins the M102 materialized proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 39af99da pins the M102 materialized proof floor guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 7d86f38e pins the current M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit c0c4dca1 records the M102 desktop trust proof citation.",
    "      - /docker/chummercomplete/chummer6-hub commit 42a3d5a4 pins the M102 desktop trust citation floor.",
    "      - /docker/chummercomplete/chummer6-hub commit af567e58 pins the M102 desktop trust verifier floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 2620a2f4 requires the M102 desktop trust verifier floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 5917695a pins the M102 current verifier floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 2ded9038 tightens M102 app-local callback proof so localhost and 127.0.0.1 install-link callbacks stay desktop-native.",
    "      - /docker/chummercomplete/chummer6-hub commit e7b5177b tightens M102 loopback callback proof so IPv6 app-local install-link callbacks stay desktop-native.",
    "      - /docker/chummercomplete/chummer6-hub commit d72386ee pins the M102 loopback callback proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit fee0655a tightens M102 app-local callback state proof so the desktop listener's state query survives grant callback continuation.",
    "      - /docker/chummercomplete/chummer6-hub commit 568b8358 tightens M102 app-local callback query-context proof.",
    "      - /docker/chummercomplete/chummer6-hub commit e0bcd91d pins the M102 callback query proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit aadffb5b pins the M102 callback query proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit a7a5ecea tightens M102 desktop trust callback proof.",
    "      - /docker/chummercomplete/chummer6-hub commit 4b9c6919 pins the M102 desktop trust callback proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit ea697985 tightens M102 receipt route proof so receipt routes must be served by top-level proof_routes.",
    "      - /docker/chummercomplete/chummer6-hub commit e9c87a3f tightens M102 served proof parity so the public proof shelf cannot drift from canonical published proof.",
    "      - /docker/chummercomplete/chummer6-hub commit d3c74d38 tightens M102 queue mirror proof so Fleet and design-owned successor queue rows cannot drift apart.",
    "      - /docker/chummercomplete/chummer6-hub commit 6b5679de tightens M102 support continuation filtering so reporter-level install-help cases cannot attach to the wrong claimed desktop install.",
    "      - /docker/chummercomplete/chummer6-hub commit 39c0ae8d tightens M102 app-local callback path proof so claimed desktop callbacks cannot drift to arbitrary localhost browser routes.",
    "      - /docker/chummercomplete/chummer6-hub commit 8e90aac9 pins the M102 app-local callback path proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit b27c5142 pins the M102 app-local proof floor guard.",
    "      - /docker/chummercomplete/chummer6-hub commit cd392a72 pins the M102 current proof floor guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 41d7ed57 pins the M102 current desktop trust floor.",
    "      - /docker/chummercomplete/chummer6-hub commit bd60fc5a tightens M102 active-run evidence path guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 2791f798 tightens M102 support intake installed-build truth.",
    "      - /docker/chummercomplete/chummer6-hub commit 93e5075a tightens M102 current proof floor guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 894dbedd pins M102 current proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 997337a6 pins M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit e24162d9 requires M102 desktop trust proof citation.",
    "      - /docker/chummercomplete/chummer6-hub commit bb8db39c tightens M102 support install matching.",
    "      - /docker/chummercomplete/chummer6-hub commit 1d6c686c tightens M102 duplicate proof citations.",
    "      - /docker/chummercomplete/chummer6-hub commit 18902a34 pins the M102 duplicate proof citation guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 72fa2471 tightens M102 proof anchor scope so canonical closure evidence cannot cite existing files outside the package allowed paths.",
    "      - /docker/chummercomplete/chummer6-hub commit c791e657 tightens M102 install receipt matching so support continuation cannot attach a newer receipt from another desktop platform.",
    "      - /docker/chummercomplete/chummer6-hub commit 438861f0 pins the M102 receipt matching proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 4238a88a pins the current M102 desktop trust proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit b8a03984 tightens M102 encoded active-run proof marker guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 6961320a tightens M102 installed-build receipt truth.",
    "      - /docker/chummercomplete/chummer6-hub commit aceef790 pins the M102 installed-build receipt proof.",
    "      - /docker/chummercomplete/chummer6-hub commit 5f9621c3 tightens M102 encoded proof marker guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 4e8eb4c1 pins the M102 encoded proof marker guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 4bede125 tightens M102 closed queue proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit ebfaaf36 pins the M102 closed queue proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 38eb0769 pins M102 current proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit ed611d1a tightens M102 support install truth matching.",
    "      - /docker/chummercomplete/chummer6-hub commit d9d6c9a0 pins M102 support truth proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit a01d80ab pins M102 support truth proof floor guard.",
    "      - /docker/chummercomplete/chummer6-hub commit a766e82c pins M102 desktop trust proof floor guard.",
    "      - /docker/chummercomplete/chummer6-hub commit d9f59d4f pins M102 desktop trust current proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit af6a480e proves the M102 native support route receipt.",
    "      - /docker/chummercomplete/chummer6-hub commit a7d27da6 guards the M102 proof package repo.",
    "      - /docker/chummercomplete/chummer6-hub commit 0bc0c858 tightens the M102 native support proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit c8ec0c6a tightens the M102 handoff proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit e08468e2 pins the M102 handoff proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 9e7d12ef guards M102 proof receipts against browser-only route closure.",
    "      - /docker/chummercomplete/chummer6-hub commit 554cd159 pins M102 native receipt proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 8e0a630e pins M102 current proof floor guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 47a831ba hardens claimed install continuation action sanitization so trusted native absolute actions survive while query and fragment install-link secrets are redacted from support continuation receipts.",
    "      - /docker/chummercomplete/chummer6-hub commit 9c0f3c17 pins the M102 receipt route proof citation.",
    "      - /docker/chummercomplete/chummer6-hub commit 2fc1d739 pins the M102 current proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit f233069f hardens M102 native support requested-action secret redaction.",
    "      - /docker/chummercomplete/chummer6-hub commit 7be45a1b hardens M102 encoded hash separator secret redaction.",
    "      - /docker/chummercomplete/chummer6-hub commit e054d2f1 pins the M102 encoded hash proof floor.",
    "      - /docker/chummercomplete/chummer6-hub commit 43e273e9 hardens M102 native support secret redaction.",
    "      - /docker/chummercomplete/chummer6-hub commit d86cce39 tightens the M102 successor frontier proof.",
    "      - /docker/chummercomplete/chummer6-hub commit aa318f30 tightens the M102 encoded proof marker guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 607139bc hardens M102 HTML hash separator redaction.",
    "      - /docker/chummercomplete/chummer6-hub commit 0a007077 tightens M102 compressed helper proof guard.",
    "      - /docker/chummercomplete/chummer6-hub commit 94dd7d42 tightens M102 compressed base32/base85 helper proof guard.",
    "      - python3 scripts/verify_desktop_native_trust_receipts.py",
    "      - python3 -m unittest tests/test_desktop_native_trust_receipts.py",
    '      - dotnet test --project Chummer.Tests/Chummer.Tests.csproj --filter "DesktopInstallRailTests|PublicLandingClaimRecoveryFlowTests|InstallLinkingContinuationVerification|InstallLinkingControllerBrowserCallbackTests" --no-restore',
]


def expected_current_proof_routes() -> list[str]:
    release_channel_path = REPO_ROOT / "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"
    if release_channel_path.is_file():
        payload = json.loads(release_channel_path.read_text(encoding="utf-8"))
        install_routes = sorted(
            {
                f"/downloads/install/{str(item.get('artifactId') or item.get('id') or '').strip()}"
                for collection_name in ("artifacts", "downloads")
                for item in payload.get(collection_name, [])
                if isinstance(item, dict)
                and str(item.get("kind") or "").strip().lower() == "installer"
                and str(item.get("artifactId") or item.get("id") or "").strip()
            }
        )
    else:
        install_routes = [
            "/downloads/install/avalonia-linux-x64-installer",
            "/downloads/install/avalonia-osx-arm64-installer",
            "/downloads/install/avalonia-win-x64-installer",
        ]
    additional_install_routes = [
        route for route in install_routes if route != "/downloads/install/avalonia-linux-x64-installer"
    ]
    return [
        "/downloads/install/avalonia-linux-x64-installer",
        "/home/access",
        "/home/work",
        "/account/access",
        "/account/work",
        "/account/support",
        "/contact",
        "/downloads",
        *additional_install_routes,
    ]
REGISTRY_102_1_LINES = [
    "milestones:",
    "  - id: 102",
    "    work_tasks:",
    "      - id: 102.1",
    "        owner: chummer6-hub",
    "        title: Unify account, claim, install, and support-case recovery into one desktop-native continuation flow.",
    "        status: complete",
    "        landed_commit: 160af58f",
    "        evidence:",
    "          - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InstallLinkingController.cs exposes /api/v1/install-linking/continuation for grant-bound claimed desktop installs with current release, update, rollback, and support continuation truth.",
    "          - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml and /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/Accounts/Account.cshtml make guided setup/app continuation the default and keep claim codes as recovery fallback only.",
    "          - /docker/chummercomplete/chummer6-hub/scripts/verify_desktop_native_trust_receipts.py fail-closes missing source markers and missing successor proof receipts for desktop_native_claim_and_recovery and support_followthrough:install_truth.",
    "          - /docker/chummercomplete/chummer6-hub/Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs covers app-local localhost and 127.0.0.1 install-link callbacks so claimed desktop users return to the app-local continuation listener instead of browser-only continuation.",
    "          - /docker/chummercomplete/chummer6-hub/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json keeps canonical flagship proof_routes on the registry surface while the M102 proof receipts carry /downloads/install/avalonia-linux-x64-installer/continue.json, /api/v1/install-linking/continuation, /account/access, /account/support, and /contact.",
    "          - /docker/chummercomplete/chummer6-hub commit e27f24c1 tightens desktop-native continuation fallback-posture proof so claimed installs return the same fallback posture used by download and support recovery.",
    "          - /docker/chummercomplete/chummer6-hub commit e578a519 tightens the completed M102 proof pin so future shards verify the closed package instead of repeating it.",
    "          - /docker/chummercomplete/chummer6-hub commit 9fcec2a0 fail-closes M102 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
    "          - /docker/chummercomplete/chummer6-hub commit 266d526b pins the M102 queue proof hardening commit so stale queue proof cannot keep the package green.",
    "          - /docker/chummercomplete/chummer6-hub commit 6ea510c8 pins the M102 telemetry guard proof evidence so future shards verify the latest closed-package guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 7a825c73 pins the M102 desktop trust guard evidence into the verifier and unit guard.",
    "          - /docker/chummercomplete/chummer6-hub commit aff39474 pins the M102 desktop trust latest guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 38d50742 pins the M102 desktop trust proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit b9404a4c pins the M102 desktop trust latest proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit e6ae11a7 pins the M102 desktop trust guard closure.",
    "          - /docker/chummercomplete/chummer6-hub commit 4c542b50 pins the latest M102 desktop trust closure guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 02bed909 pins the M102 desktop trust closure guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 2017cdfe requires the latest M102 desktop trust proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 24432002 tightens the current M102 desktop trust proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 4afd6c3e pins the current M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit d99d080e pins the M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit b5b25e98 tightens M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit d7cb9d6e pins M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit ec81b660 pins M102 desktop trust current proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit b2d5cbfc tightens M102 generated proof hygiene.",
    "          - /docker/chummercomplete/chummer6-hub commit 5eac0f47 pins M102 desktop trust current proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 91514d42 pins M102 desktop trust proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit f7031d74 pins M102 desktop trust guard floor.",
    "          - /docker/chummercomplete/chummer6-hub commit f169b4a0 requires the current M102 desktop trust guard.",
    "          - /docker/chummercomplete/chummer6-hub commit b473e033 pins the current M102 desktop trust guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 782fa007 requires the current M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 26817b22 pins M102 desktop trust current proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 6cf10549 pins M102 desktop trust 268 proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit de9653ee pins M102 desktop trust latest proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 3760ef63 tightens M102 active-run proof marker matching so queue, registry, and generated proof evidence reject helper references regardless of casing.",
    "          - /docker/chummercomplete/chummer6-hub commit 0337eeb5 pins the M102 active-run casing proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit ad21e50f pins the M102 active-run casing proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 51c46e74 pins the M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit ed3989d9 pins the M102 desktop trust proof floor guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 653b23f0 tightens M102 desktop trust proof floor guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 1a1c5615 pins M102 desktop trust current proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit ed689925 pins M102 desktop trust latest proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 461e3709 pins M102 desktop trust current proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 171c2de0 tightens M102 blocked run-helper proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 73f1ee9a pins M102 desktop trust proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 74dff34c tightens M102 forbidden command evidence guard.",
    "          - /docker/chummercomplete/chummer6-hub commit aea02326 pins the M102 forbidden command proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 2330a11c pins the current M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 99a03a04 pins the M102 current desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 0dca4b42 pins the M102 landed proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 2c351c92 pins M102 landed proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 575daa11 pins M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit bffcad4d tightens M102 proof timestamp stability so generatedAt-only proof refreshes do not reopen the closed desktop-native trust package.",
    "          - /docker/chummercomplete/chummer6-hub commit 9454feb7 pins M102 timestamp proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit f1513793 pins M102 timestamp proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 7ddbc973 pins M102 current proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 01800bd9 pins M102 current desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit c9bbf63c tightens M102 served proof shelf route guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 2f7ed420 tightens M102 duplicate package-row proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 15c5f0e5 tightens M102 generated proof uniqueness so duplicate package or receipt rows fail closed.",
    "          - /docker/chummercomplete/chummer6-hub commit a270dcd0 tightens M102 desktop callback proof so app-local install-link callbacks cannot drift back to browser-only continuation.",
    "          - /docker/chummercomplete/chummer6-hub commit 4fa19f0c pins M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 6f468ee9 tightens M102 worker-state proof guard so run-state helper output cannot close desktop-native trust evidence.",
    "          - /docker/chummercomplete/chummer6-hub commit 4ed1f541 pins the M102 supervisor proof guard floor so future shards verify the current completed-package guard.",
    "          - /docker/chummercomplete/chummer6-hub commit f3300fd9 pins the M102 supervisor proof guard into the verifier and unit guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 06fa0634 pins the M102 local proof floor guard.",
    "          - /docker/chummercomplete/chummer6-hub commit f23b6dc4 records the M102 proof floor in the verifier.",
    "          - /docker/chummercomplete/chummer6-hub commit 7cf5461b pins the M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit cae283e9 requires the current M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit e908400b pins the M102 current desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 1870132d pins the latest M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 6b811ca2 pins the latest M102 desktop trust guard floor.",
    "          - /docker/chummercomplete/chummer6-hub commit b7107364 pins the M102 desktop trust guard floor.",
    "          - /docker/chummercomplete/chummer6-hub commit f49c64a9 pins the M102 current desktop trust guard floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 512f3569 pins the M102 current desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit ff9c3313 pins the M102 latest desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit de158f6b tightens M102 worker-context proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 8a542230 pins the M102 worker-context proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 74c3b75b pins the M102 worker-context proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 76b350fc tightens M102 materialized proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit d3b19c88 pins the M102 materialized proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 39af99da pins the M102 materialized proof floor guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 7d86f38e pins the current M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit c0c4dca1 records the M102 desktop trust proof citation.",
    "          - /docker/chummercomplete/chummer6-hub commit 42a3d5a4 pins the M102 desktop trust citation floor.",
    "          - /docker/chummercomplete/chummer6-hub commit af567e58 pins the M102 desktop trust verifier floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 2620a2f4 requires the M102 desktop trust verifier floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 5917695a pins the M102 current verifier floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 2ded9038 tightens M102 app-local callback proof so localhost and 127.0.0.1 install-link callbacks stay desktop-native.",
    "          - /docker/chummercomplete/chummer6-hub commit e7b5177b tightens M102 loopback callback proof so IPv6 app-local install-link callbacks stay desktop-native.",
    "          - /docker/chummercomplete/chummer6-hub commit d72386ee pins the M102 loopback callback proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit fee0655a tightens M102 app-local callback state proof so the desktop listener's state query survives grant callback continuation.",
    "          - /docker/chummercomplete/chummer6-hub commit 568b8358 tightens M102 app-local callback query-context proof.",
    "          - /docker/chummercomplete/chummer6-hub commit e0bcd91d pins the M102 callback query proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit aadffb5b pins the M102 callback query proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit a7a5ecea tightens M102 desktop trust callback proof.",
    "          - /docker/chummercomplete/chummer6-hub commit 4b9c6919 pins the M102 desktop trust callback proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit ea697985 tightens M102 receipt route proof so receipt routes must be served by top-level proof_routes.",
    "          - /docker/chummercomplete/chummer6-hub commit e9c87a3f tightens M102 served proof parity so the public proof shelf cannot drift from canonical published proof.",
    "          - /docker/chummercomplete/chummer6-hub commit d3c74d38 tightens M102 queue mirror proof so Fleet and design-owned successor queue rows cannot drift apart.",
    "          - /docker/chummercomplete/chummer6-hub commit 6b5679de tightens M102 support continuation filtering so reporter-level install-help cases cannot attach to the wrong claimed desktop install.",
    "          - /docker/chummercomplete/chummer6-hub commit 39c0ae8d tightens M102 app-local callback path proof so claimed desktop callbacks cannot drift to arbitrary localhost browser routes.",
    "          - /docker/chummercomplete/chummer6-hub commit 8e90aac9 pins the M102 app-local callback path proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit b27c5142 pins the M102 app-local proof floor guard.",
    "          - /docker/chummercomplete/chummer6-hub commit cd392a72 pins the M102 current proof floor guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 41d7ed57 pins the M102 current desktop trust floor.",
    "          - /docker/chummercomplete/chummer6-hub commit bd60fc5a tightens M102 active-run evidence path guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 2791f798 tightens M102 support intake installed-build truth.",
    "          - /docker/chummercomplete/chummer6-hub commit 93e5075a tightens M102 current proof floor guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 894dbedd pins M102 current proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 997337a6 pins M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit e24162d9 requires M102 desktop trust proof citation.",
    "          - /docker/chummercomplete/chummer6-hub commit bb8db39c tightens M102 support install matching.",
    "          - /docker/chummercomplete/chummer6-hub commit 1d6c686c tightens M102 duplicate proof citations.",
    "          - /docker/chummercomplete/chummer6-hub commit 18902a34 pins the M102 duplicate proof citation guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 72fa2471 tightens M102 proof anchor scope so canonical closure evidence cannot cite existing files outside the package allowed paths.",
    "          - /docker/chummercomplete/chummer6-hub commit c791e657 tightens M102 install receipt matching so support continuation cannot attach a newer receipt from another desktop platform.",
    "          - /docker/chummercomplete/chummer6-hub commit 438861f0 pins the M102 receipt matching proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 4238a88a pins the current M102 desktop trust proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit b8a03984 tightens M102 encoded active-run proof marker guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 6961320a tightens M102 installed-build receipt truth.",
    "          - /docker/chummercomplete/chummer6-hub commit aceef790 pins the M102 installed-build receipt proof.",
    "          - /docker/chummercomplete/chummer6-hub commit 5f9621c3 tightens M102 encoded proof marker guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 4e8eb4c1 pins the M102 encoded proof marker guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 4bede125 tightens M102 closed queue proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit ebfaaf36 pins the M102 closed queue proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 38eb0769 pins M102 current proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit ed611d1a tightens M102 support install truth matching.",
    "          - /docker/chummercomplete/chummer6-hub commit d9d6c9a0 pins M102 support truth proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit a01d80ab pins M102 support truth proof floor guard.",
    "          - /docker/chummercomplete/chummer6-hub commit a766e82c pins M102 desktop trust proof floor guard.",
    "          - /docker/chummercomplete/chummer6-hub commit d9f59d4f pins M102 desktop trust current proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit af6a480e proves the M102 native support route receipt.",
    "          - /docker/chummercomplete/chummer6-hub commit a7d27da6 guards the M102 proof package repo.",
    "          - /docker/chummercomplete/chummer6-hub commit 0bc0c858 tightens the M102 native support proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit c8ec0c6a tightens the M102 handoff proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit e08468e2 pins the M102 handoff proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 9e7d12ef guards M102 proof receipts against browser-only route closure.",
    "          - /docker/chummercomplete/chummer6-hub commit 554cd159 pins M102 native receipt proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 8e0a630e pins M102 current proof floor guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 47a831ba hardens claimed install continuation action sanitization so trusted native absolute actions survive while query and fragment install-link secrets are redacted from support continuation receipts.",
    "          - /docker/chummercomplete/chummer6-hub commit 9c0f3c17 pins the M102 receipt route proof citation.",
    "          - /docker/chummercomplete/chummer6-hub commit 2fc1d739 pins the M102 current proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit f233069f hardens M102 native support requested-action secret redaction.",
    "          - /docker/chummercomplete/chummer6-hub commit 7be45a1b hardens M102 encoded hash separator secret redaction.",
    "          - /docker/chummercomplete/chummer6-hub commit e054d2f1 pins the M102 encoded hash proof floor.",
    "          - /docker/chummercomplete/chummer6-hub commit 43e273e9 hardens M102 native support secret redaction.",
    "          - /docker/chummercomplete/chummer6-hub commit d86cce39 tightens the M102 successor frontier proof.",
    "          - /docker/chummercomplete/chummer6-hub commit aa318f30 tightens the M102 encoded proof marker guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 607139bc hardens M102 HTML hash separator redaction.",
    "          - /docker/chummercomplete/chummer6-hub commit 0a007077 tightens M102 compressed helper proof guard.",
    "          - /docker/chummercomplete/chummer6-hub commit 94dd7d42 tightens M102 compressed base32/base85 helper proof guard.",
    "          - python3 scripts/verify_desktop_native_trust_receipts.py and python3 -m unittest tests/test_desktop_native_trust_receipts.py exit 0.",
    '          - dotnet test --project Chummer.Tests/Chummer.Tests.csproj --filter "DesktopInstallRailTests|PublicLandingClaimRecoveryFlowTests|InstallLinkingContinuationVerification|InstallLinkingControllerBrowserCallbackTests" --no-restore exits 0 for net10.0 and net10.0-windows.',
]
ABSOLUTE_REPO_PREFIX = "/docker/chummercomplete/chummer6-hub/"


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

        self.assertEqual("94dd7d42", verifier._current_local_proof_floor_commit())
        self.assertEqual(
            "Tighten M102 compressed base32/base85 helper proof guard",
            verifier.CURRENT_LOCAL_PROOF_FLOOR_SUBJECT,
        )
        self.assertIn("94dd7d42", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("607139bc", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("aa318f30", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("d86cce39", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("43e273e9", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("e054d2f1", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("7be45a1b", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("f233069f", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("2fc1d739", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("9c0f3c17", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("47a831ba", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("554cd159", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("9e7d12ef", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("e08468e2", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("c8ec0c6a", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("0bc0c858", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("a7d27da6", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("af6a480e", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("d9f59d4f", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("a766e82c", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("a01d80ab", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("d9d6c9a0", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("ed611d1a", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("38eb0769", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("ebfaaf36", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("4bede125", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("4e8eb4c1", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("5f9621c3", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("aceef790", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("6961320a", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("b8a03984", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("4238a88a", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("17044a9f", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("438861f0", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("c791e657", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("72fa2471", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("18902a34", verifier.REQUIRED_RESOLVING_COMMITS)
        self.assertIn("1d6c686c", verifier.REQUIRED_RESOLVING_COMMITS)
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
            any("commit a7d27da6 guards the M102 proof package repo" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit a7d27da6 guards the M102 proof package repo" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit 0bc0c858 tightens the M102 native support proof guard" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit 0bc0c858 tightens the M102 native support proof guard" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit e08468e2 pins the M102 handoff proof floor" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit e08468e2 pins the M102 handoff proof floor" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit 9e7d12ef guards M102 proof receipts against browser-only route closure" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit 9e7d12ef guards M102 proof receipts against browser-only route closure" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit 554cd159 pins M102 native receipt proof floor" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit 554cd159 pins M102 native receipt proof floor" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit 47a831ba hardens claimed install continuation action sanitization" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit 47a831ba hardens claimed install continuation action sanitization" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit 9c0f3c17 pins the M102 receipt route proof citation" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit 9c0f3c17 pins the M102 receipt route proof citation" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit f233069f hardens M102 native support requested-action secret redaction" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit f233069f hardens M102 native support requested-action secret redaction" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit 7be45a1b hardens M102 encoded hash separator secret redaction" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit 7be45a1b hardens M102 encoded hash separator secret redaction" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit e054d2f1 pins the M102 encoded hash proof floor" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit e054d2f1 pins the M102 encoded hash proof floor" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit 43e273e9 hardens M102 native support secret redaction" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit 43e273e9 hardens M102 native support secret redaction" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit d86cce39 tightens the M102 successor frontier proof" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit d86cce39 tightens the M102 successor frontier proof" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit aa318f30 tightens the M102 encoded proof marker guard" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit aa318f30 tightens the M102 encoded proof marker guard" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit 607139bc hardens M102 HTML hash separator redaction" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit 607139bc hardens M102 HTML hash separator redaction" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit 0a007077 tightens M102 compressed helper proof guard" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit 0a007077 tightens M102 compressed helper proof guard" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )
        self.assertTrue(
            any("commit 94dd7d42 tightens M102 compressed base32/base85 helper proof guard" in value for value in verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        )
        self.assertTrue(
            any("commit 94dd7d42 tightens M102 compressed base32/base85 helper proof guard" in value for value in verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        )

    def test_forbidden_active_run_marker_matching_normalizes_separators(self) -> None:
        verifier = load_verifier_module()

        markers = verifier._forbidden_markers_in_text(
            "ACTIVE RUN HELPER output from task local telemetry, "
            "active_run_handoff.generated.md, run ooda design supervisor until quiet, "
            "current steering focus with profile focus owner focus text focus, "
            "assigned successor queue package, and execution rules inside this run"
        )

        self.assertIn("active-run helper", markers)
        self.assertIn("task-local telemetry", markers)
        self.assertIn("ACTIVE_RUN_HANDOFF", markers)
        self.assertIn("run_ooda_design_supervisor_until_quiet", markers)
        self.assertIn("current steering focus", markers)
        self.assertIn("profile focus", markers)
        self.assertIn("owner focus", markers)
        self.assertIn("text focus", markers)
        self.assertIn("assigned successor queue package", markers)
        self.assertIn("execution rules inside this run", markers)
        self.assertNotIn("remaining milestones", markers)

    def test_forbidden_active_run_marker_matching_decodes_encoded_text(self) -> None:
        verifier = load_verifier_module()

        markers = verifier._forbidden_markers_in_text(
            "TASK%5FLOCAL%5FTELEMETRY and "
            "active-run%20helper&#32;commands with "
            "run%5Fooda%5Fdesign%5Fsupervisor%5Funtil%5Fquiet"
        )

        self.assertIn("TASK_LOCAL_TELEMETRY", markers)
        self.assertIn("active-run helper commands", markers)
        self.assertIn("run_ooda_design_supervisor_until_quiet", markers)

    def test_forbidden_active_run_marker_matching_decodes_base64_text(self) -> None:
        verifier = load_verifier_module()

        markers = verifier._forbidden_markers_in_text(
            "VEFTS19MT0NBTF9URUxFTUVUUlkuZ2VuZXJhdGVkLmpzb24= "
            "YWN0aXZlLXJ1biBoZWxwZXIgY29tbWFuZHM "
            "cnVuX29vZGFfZGVzaWduX3N1cGVydmlzb3JfdW50aWxfcXVpZXQ"
        )

        self.assertIn("TASK_LOCAL_TELEMETRY", markers)
        self.assertIn("active-run helper commands", markers)
        self.assertIn("run_ooda_design_supervisor_until_quiet", markers)

    def test_forbidden_active_run_marker_matching_decodes_base32_and_base85_text(self) -> None:
        verifier = load_verifier_module()
        base32_marker = base64.b32encode(b"TASK_LOCAL_TELEMETRY.generated.json").decode("ascii")
        base85_marker = base64.b85encode(b"active-run helper commands").decode("ascii")
        ascii85_marker = base64.a85encode(b"run_ooda_design_supervisor_until_quiet").decode("ascii")

        markers = verifier._forbidden_markers_in_text(
            f"{base32_marker} {base85_marker} {ascii85_marker}"
        )

        self.assertIn("TASK_LOCAL_TELEMETRY", markers)
        self.assertIn("active-run helper commands", markers)
        self.assertIn("run_ooda_design_supervisor_until_quiet", markers)

    def test_forbidden_active_run_marker_matching_decodes_compressed_base64_text(self) -> None:
        verifier = load_verifier_module()
        compressed_marker = base64.b64encode(
            zlib.compress(b"TASK_LOCAL_TELEMETRY generated active-run helper commands")
        ).decode("ascii")

        markers = verifier._forbidden_markers_in_text(compressed_marker)

        self.assertIn("TASK_LOCAL_TELEMETRY", markers)
        self.assertIn("active-run helper commands", markers)

    def test_forbidden_active_run_marker_matching_decodes_compressed_base32_and_base85_text(self) -> None:
        verifier = load_verifier_module()
        compressed_task_local = zlib.compress(b"TASK_LOCAL_TELEMETRY generated status query")
        compressed_helper = zlib.compress(b"active-run helper commands")
        compressed_supervisor = zlib.compress(b"run_ooda_design_supervisor_until_quiet")
        base32_marker = base64.b32encode(compressed_task_local).decode("ascii")
        base85_marker = base64.b85encode(compressed_helper).decode("ascii")
        ascii85_marker = base64.a85encode(compressed_supervisor).decode("ascii")

        markers = verifier._forbidden_markers_in_text(
            f"{base32_marker} {base85_marker} {ascii85_marker}"
        )

        self.assertIn("TASK_LOCAL_TELEMETRY", markers)
        self.assertIn("status query", markers)
        self.assertIn("active-run helper commands", markers)
        self.assertIn("run_ooda_design_supervisor_until_quiet", markers)

    def test_canonical_yaml_block_rejects_encoded_active_run_markers(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            queue_path.write_text(
                "\n".join(
                    [
                        "items:",
                        "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                        "    package_id: next90-m102-hub-desktop-native-trust",
                        "    proof:",
                        "      - TASK%5FLOCAL%5FTELEMETRY.generated.json",
                        "      - active-run%20helper&#32;commands",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            errors: list[str] = []

            verifier._verify_marker_block(
                errors,
                queue_path,
                "package_id: next90-m102-hub-desktop-native-trust",
                ["package_id: next90-m102-hub-desktop-native-trust"],
                "successor queue staging",
                forbidden_markers=verifier.FORBIDDEN_PROOF_MARKERS,
            )

        self.assertIn(
            "canonical successor queue staging block has forbidden active-run proof marker: TASK_LOCAL_TELEMETRY",
            errors,
        )
        self.assertIn(
            "canonical successor queue staging block has forbidden active-run proof marker: active-run helper commands",
            errors,
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
            self.assertEqual("chummer6-hub", payload["package_repo"])
            self.assertEqual(expected_current_proof_routes(), payload["proof_routes"])
            m102_package = next(
                item
                for item in payload["successor_queue_packages"]
                if item["package_id"] == "next90-m102-hub-desktop-native-trust"
            )
            self.assertEqual(
                m102_package,
                payload["successor_queue_packages_by_id"]["next90-m102-hub-desktop-native-trust"],
            )
            self.assertEqual("complete", m102_package["status"])
            self.assertEqual(2897065929, m102_package["frontier_id"])
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
            m102_receipts = [
                receipt
                for receipt in payload["proof_receipts"]
                if receipt["package_id"] == "next90-m102-hub-desktop-native-trust"
            ]
            self.assertEqual(
                {
                    "desktop_native_claim_and_recovery",
                    "support_followthrough:install_truth",
                    "desktop_client_readiness:bounded_routes",
                    "fleet_and_operator_loop:desktop_native_trust",
                },
                {receipt["receipt_id"] for receipt in m102_receipts},
            )
            self.assertTrue(all(receipt["frontier_id"] == 2897065929 for receipt in m102_receipts))
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

    def test_proof_payload_fail_closes_browser_only_receipt_routes(self) -> None:
        verifier = load_verifier_module()
        proof_receipts = []
        for receipt_id, expected in verifier.REQUIRED_PROOF_RECEIPTS.items():
            proof_receipts.append(
                {
                    "receipt_id": receipt_id,
                    "package_id": expected["package_id"],
                    "milestone_id": expected["milestone_id"],
                    "frontier_id": expected["frontier_id"],
                    "summary": expected["summary"],
                    "surfaces": list(expected["surfaces"]),
                    "routes": ["/account/access"] if receipt_id == "desktop_native_claim_and_recovery" else list(expected["routes"]),
                }
            )

        proof = {
            "package_repo": verifier.REQUIRED_PROOF_PACKAGE_REPO,
            "proof_routes": list(verifier.REQUIRED_TOP_LEVEL_PROOF_ROUTES),
            "journeys_passed": list(verifier.REQUIRED_TOP_LEVEL_JOURNEYS),
            "successor_queue_packages": [dict(verifier.REQUIRED_PROOF_PACKAGE)],
            "successor_queue_packages_by_id": {
                verifier.PACKAGE_ID: dict(verifier.REQUIRED_PROOF_PACKAGE),
            },
            "proof_receipts": proof_receipts,
        }
        errors: list[str] = []

        verifier._verify_m102_proof_payload(errors, proof, "mutated proof")

        self.assertIn(
            "mutated proof desktop_native_claim_and_recovery routes do not include a grant-bound native install-linking route",
            errors,
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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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

    def test_extract_yaml_block_handles_zero_indented_canonical_queue_items(self) -> None:
        verifier = load_verifier_module()

        queue_text = "\n".join(
            [
                "items:",
                "- title: Unify claim, install, update, and support recovery into one desktop-native flow",
                "  task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                "  package_id: next90-m102-hub-desktop-native-trust",
                "  proof:",
                "  - queue-proof-a",
                "  - queue-proof-b",
                "  allowed_paths:",
                "  - Chummer.Run.Api",
                "  - scripts",
                "- title: Another package",
                "  package_id: next90-m999-something-else",
            ]
        )

        block = verifier._extract_yaml_block(queue_text, "package_id: next90-m102-hub-desktop-native-trust")

        self.assertIsNotNone(block)
        self.assertEqual(["queue-proof-a", "queue-proof-b"], verifier._extract_yaml_string_list(block, "proof"))
        self.assertEqual(["Chummer.Run.Api", "scripts"], verifier._extract_yaml_string_list(block, "allowed_paths"))

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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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

    def test_verifier_fail_closes_successor_queue_eta_status_drift(self) -> None:
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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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
            eta_drift_queue = complete_queue.replace(
                "    frontier_id: 2897065929\n",
                "    frontier_id: 2897065929\n    eta: 5.6d-2w\n",
            )
            queue_path.write_text(eta_drift_queue + "\n", encoding="utf-8")
            design_queue_path.write_text(eta_drift_queue + "\n", encoding="utf-8")
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
                "canonical successor queue staging block has forbidden active-run proof marker: eta",
                result.stderr,
            )
            self.assertIn(
                "canonical design successor queue staging block has forbidden active-run proof marker: eta",
                result.stderr,
            )

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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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

    def test_verifier_fail_closes_successor_registry_title_drift(self) -> None:
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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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
                "\n".join(REGISTRY_102_1_LINES).replace(
                    "        title: Unify account, claim, install, and support-case recovery into one desktop-native continuation flow.",
                    "        title: Reopen browser claim fallback whenever install proof looks stale.",
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
                "canonical successor registry block missing marker: "
                "title: Unify account, claim, install, and support-case recovery into one desktop-native continuation flow.",
                result.stderr,
            )

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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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
                    "      - task-local telemetry first_commands and frontier_briefs with remaining milestones, remaining queue items, critical path, successor frontier detail, and shard runtime handoff\n"
                    "      - Run id 20260417T194405Z-shard-1 selected account acct-chatgpt-core selected model gpt-5.4 prompt path /tmp/prompt.txt recent stderr tail\n"
                    "      - current steering focus with profile focus, owner focus, text focus, assigned successor queue package, execution rules inside this run, and operator/OODA loop owns telemetry\n",
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
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: Run id",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: Selected account",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: Selected model",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: Prompt path",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: Recent stderr tail",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: current steering focus",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: profile focus",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: owner focus",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: text focus",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: assigned successor queue package",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: execution rules inside this run",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: operator/OODA loop",
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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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
                    "    completion_action: verify_closed_package_only",
                    "    do_not_reopen_reason: M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
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
                        "          - Run id 20260417T194405Z-shard-1 selected account acct-chatgpt-core selected model gpt-5.4 prompt path /tmp/prompt.txt recent stderr tail",
                        "          - Current steering focus with profile focus, owner focus, text focus, assigned successor queue package, execution rules inside this run, and operator/OODA loop owns telemetry",
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
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: Run id",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: Selected account",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: Selected model",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: Prompt path",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: Recent stderr tail",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: current steering focus",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: profile focus",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: owner focus",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: text focus",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: assigned successor queue package",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: execution rules inside this run",
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
                    "CHUMMER_HUB_SERVED_RELEASE_PROOF_PATH": str(proof_path),
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
                    "CHUMMER_HUB_SERVED_RELEASE_PROOF_PATH": str(proof_path),
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

    def test_verifier_fail_closes_generated_m102_package_index_drift(self) -> None:
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
            proof["successor_queue_packages_by_id"]["next90-m102-hub-desktop-native-trust"]["landed_commit"] = "stale"
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
            self.assertIn("indexed proof package has wrong landed_commit", result.stderr)
            self.assertIn(
                "successor_queue_packages_by_id[next90-m102-hub-desktop-native-trust] must mirror "
                "successor_queue_packages[next90-m102-hub-desktop-native-trust] exactly",
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

    def test_verifier_fail_closes_generated_receipt_package_orphan(self) -> None:
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
            orphan_receipt = next(
                item
                for item in proof["proof_receipts"]
                if item["receipt_id"] == "support_followthrough:install_truth"
            )
            orphan_receipt["package_id"] = "next90-m999-hub-orphaned-receipt"
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
                "published proof file receipt 'support_followthrough:install_truth' references package_id "
                "not listed in successor_queue_packages: next90-m999-hub-orphaned-receipt",
                result.stderr,
            )
            self.assertIn(
                "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from scripts/materialize_hub_local_release_proof.py",
                result.stderr,
            )

    def test_verifier_allows_generated_at_timestamp_only_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            readiness_path = load_verifier_module()._flagship_readiness_path()
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
                env={
                    **dict(os.environ),
                    "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH": str(readiness_path),
                },
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["generatedAt"] = "2099-01-01T00:00:00Z"
            proof["generated_at"] = "2099-01-01T00:00:00Z"
            proof["desktop_client_readiness"]["generated_at"] = "2099-01-01T00:00:00Z"
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
                    "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH": str(readiness_path),
                },
            )

            self.assertEqual(
                0,
                result.returncode,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertIn("desktop native trust receipts verified", result.stdout)
            self.assertNotIn(
                "served HUB_LOCAL_RELEASE_PROOF.generated.json drifts from "
                "published HUB_LOCAL_RELEASE_PROOF.generated.json for next90-m102-hub-desktop-native-trust",
                result.stderr,
            )

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

    def test_verifier_fail_closes_top_level_package_without_receipts(self) -> None:
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
            proof["successor_queue_package"]["package_id"] = "next90-m999-hub-unproven-top-level"
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
                "published proof file top-level successor_queue_package package_id is not listed in "
                "successor_queue_packages: next90-m999-hub-unproven-top-level",
                result.stderr,
            )
            self.assertIn(
                "published proof file top-level successor_queue_package package_id has no proof_receipts: "
                "next90-m999-hub-unproven-top-level",
                result.stderr,
            )
            self.assertIn(
                "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from scripts/materialize_hub_local_release_proof.py",
                result.stderr,
            )

    def test_verifier_fail_closes_generated_package_repo_drift(self) -> None:
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
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                0,
                materialize.returncode,
                msg=f"materializer stderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["package_repo"] = "fleet"
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(VERIFY_SCRIPT),
                ],
                cwd=REPO_ROOT,
                env={
                    **os.environ,
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                    "CHUMMER_HUB_SERVED_RELEASE_PROOF_PATH": str(proof_path),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "published proof file has wrong package_repo: expected 'chummer6-hub', got 'fleet'",
                result.stderr,
            )
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
                "Run id 20260417T194405Z-shard-1 selected account acct-chatgpt-core selected model gpt-5.4 prompt path /tmp/prompt.txt recent stderr tail",
                "Current steering focus with profile focus, owner focus, text focus, assigned successor queue package, execution rules inside this run, and operator/OODA loop owns telemetry",
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
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[4]: Run id",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[4]: Selected account",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[4]: Selected model",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[4]: Prompt path",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[4]: Recent stderr tail",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[5]: current steering focus",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[5]: profile focus",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[5]: owner focus",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[5]: text focus",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[5]: assigned successor queue package",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[5]: execution rules inside this run",
                result.stderr,
            )
            self.assertIn(
                "published proof file has forbidden active-run proof marker "
                "at $.proof_receipts[1].evidence[5]: operator/OODA loop",
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
                if route != "/home/access"
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
                "served release proof file proof_routes missing canonical flagship route: "
                "/home/access",
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
                "/docker/chummercomplete/chummer6-hub/tests/test_desktop_native_trust_receipts.py",
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
                "1d6c686c",
                "18902a34",
                "72fa2471",
                "c791e657",
                "438861f0",
                "17044a9f",
                "4238a88a",
                "b8a03984",
                "6961320a",
                "aceef790",
                "5f9621c3",
                "4e8eb4c1",
                "4bede125",
                "ebfaaf36",
                "38eb0769",
                "ed611d1a",
                "d9d6c9a0",
                "a01d80ab",
                "a766e82c",
                "d9f59d4f",
                "af6a480e",
                "a7d27da6",
                "0bc0c858",
                "c8ec0c6a",
                "e08468e2",
                "9e7d12ef",
                "554cd159",
                "8e0a630e",
                "47a831ba",
                "9c0f3c17",
                "2fc1d739",
                "f233069f",
                "7be45a1b",
                "e054d2f1",
                "43e273e9",
                "d86cce39",
                "aa318f30",
                "607139bc",
                "0a007077",
                "94dd7d42",
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
                "/docker/chummercomplete/chummer6-hub commit 1d6c686c duplicate proof row."
            ]
            verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"] = original_registry_evidence + [
                "/docker/chummercomplete/chummer6-hub commit 1d6c686c duplicate proof row."
            ]
            errors: list[str] = []
            verifier._verify_canonical_commit_floor_consistency(errors)

            self.assertIn(
                "M102 canonical queue proof has duplicate commit citations: ['1d6c686c']",
                errors,
            )
            self.assertIn(
                "M102 canonical registry proof has duplicate commit citations: ['1d6c686c']",
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

    def test_verifier_fail_closes_repo_proof_anchors_outside_allowed_scope(self) -> None:
        verifier = load_verifier_module()
        original_queue_proof = list(verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
        original_registry_evidence = list(verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
        out_of_scope_anchor = "/docker/chummercomplete/chummer6-hub/Chummer.Play.Contracts/Chummer.Play.Contracts.csproj"

        try:
            verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"] = original_queue_proof + [
                out_of_scope_anchor
            ]
            verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"] = original_registry_evidence + [
                f"{out_of_scope_anchor} should not close the M102 desktop-native trust package."
            ]

            with tempfile.TemporaryDirectory() as temp_root:
                repo_root = Path(temp_root)
                path = repo_root / "Chummer.Play.Contracts/Chummer.Play.Contracts.csproj"
                path.parent.mkdir(parents=True)
                path.write_text("<Project />\n", encoding="utf-8")

                errors: list[str] = []
                verifier._verify_required_repo_anchor_paths(errors, repo_root)

            self.assertIn(
                "canonical proof anchor is outside the M102 allowed paths: "
                f"{out_of_scope_anchor}",
                errors,
            )
        finally:
            verifier.REQUIRED_CANONICAL_QUEUE_LISTS["proof"] = original_queue_proof
            verifier.REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"] = original_registry_evidence

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

    def test_current_sources_satisfy_authority_aware_desktop_native_markers(self) -> None:
        verifier = load_verifier_module()
        errors: list[str] = []

        verifier._verify_required_source_markers(errors, REPO_ROOT)

        self.assertEqual([], errors)

    def test_verifier_fail_closes_review_required_primary_action_tamper(self) -> None:
        verifier = load_verifier_module()
        controller_path = Path("Chummer.Run.Api/Controllers/InstallLinkingController.cs")
        required_marker = (
            "NativePrimaryActionHref: releaseAvailabilityAllowed ? "
            "BuildNativeContinuationPrimaryActionHref(updateAvailable, leadSupportCase) "
            ": NativeContinuationHref"
        )

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path in verifier.REQUIRED_SOURCE_MARKERS:
                source = REPO_ROOT / relative_path
                target = repo_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            controller = repo_root / controller_path
            source = controller.read_text(encoding="utf-8")
            bounded_false_branch = (
                "NativePrimaryActionHref: releaseAvailabilityAllowed\n"
                "                ? BuildNativeContinuationPrimaryActionHref(updateAvailable, leadSupportCase)\n"
                "                : NativeContinuationHref,"
            )
            normal_primary_action = (
                "NativePrimaryActionHref: releaseAvailabilityAllowed\n"
                "                ? BuildNativeContinuationPrimaryActionHref(updateAvailable, leadSupportCase)\n"
                "                : BuildNativeContinuationPrimaryActionHref(updateAvailable, leadSupportCase),"
            )
            self.assertIn(bounded_false_branch, source)
            controller.write_text(
                source.replace(bounded_false_branch, normal_primary_action, 1),
                encoding="utf-8",
            )

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

        self.assertIn(f"{controller_path} missing marker: {required_marker}", errors)

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
                        if marker != "Use Installs only to relink or reclaim that copy, and keep browser pages as backup help instead of the normal path."
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Views/Accounts/Account.cshtml missing marker: "
                "Use Installs only to relink or reclaim that copy, and keep browser pages as backup help instead of the normal path.",
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

    def test_verifier_fail_closes_native_support_route_receipt_drift(self) -> None:
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
                        if marker
                        != "Native route receipt: support {NativeSupportHref}; update {NativeUpdateHref}; rollback {NativeRollbackHref}; recovery {NativeRecoveryHref}; account, downloads, and public support links are human fallback only."
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Controllers/InstallLinkingController.cs missing marker: "
                "Native route receipt: support {NativeSupportHref}; update {NativeUpdateHref}; rollback {NativeRollbackHref}; recovery {NativeRecoveryHref}; account, downloads, and public support links are human fallback only.",
                errors,
            )

    def test_verifier_fail_closes_install_id_only_support_truth_drift(self) -> None:
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
                        if marker != "HasSupportCaseInstallTruth(supportCase)"
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Controllers/InstallLinkingController.cs missing marker: "
                "HasSupportCaseInstallTruth(supportCase)",
                errors,
            )

    def test_verifier_fail_closes_insecure_public_native_action_drift(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == Path("tests/RunServicesVerification/InstallLinkingContinuationVerification.cs"):
                    markers = [
                        marker
                        for marker in markers
                        if marker != "Native support action sanitizer should fail closed instead of preserving insecure public Hub-native actions."
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "tests/RunServicesVerification/InstallLinkingContinuationVerification.cs missing marker: "
                "Native support action sanitizer should fail closed instead of preserving insecure public Hub-native actions.",
                errors,
            )

    def test_verifier_fail_closes_native_query_state_action_drift(self) -> None:
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
                        if marker != "NativeInstallRailPathForValidation(trimmed)"
                    ]
                if relative_path == Path("tests/RunServicesVerification/InstallLinkingContinuationVerification.cs"):
                    markers = [
                        marker
                        for marker in markers
                        if marker != "Native support action sanitizer should preserve native support paths when encoded slash state appears only in query or fragment context."
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Controllers/InstallLinkingController.cs missing marker: "
                "NativeInstallRailPathForValidation(trimmed)",
                errors,
            )
            self.assertIn(
                "tests/RunServicesVerification/InstallLinkingContinuationVerification.cs missing marker: "
                "Native support action sanitizer should preserve native support paths when encoded slash state appears only in query or fragment context.",
                errors,
            )

    def test_verifier_fail_closes_html_entity_equals_candidate_drift(self) -> None:
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
                        if marker != 'component.Contains("&equals;", StringComparison.OrdinalIgnoreCase)'
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Controllers/InstallLinkingController.cs missing marker: "
                'component.Contains("&equals;", StringComparison.OrdinalIgnoreCase)',
                errors,
            )

    def test_verifier_fail_closes_html_numeric_hash_separator_drift(self) -> None:
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
                        if marker != 'remaining.StartsWith("&#35;", StringComparison.OrdinalIgnoreCase)'
                    ]
                if relative_path == Path("tests/RunServicesVerification/InstallLinkingContinuationVerification.cs"):
                    markers = [
                        marker
                        for marker in markers
                        if marker != "Native support case should redact claim-code values after HTML decimal hash separators."
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Controllers/InstallLinkingController.cs missing marker: "
                'remaining.StartsWith("&#35;", StringComparison.OrdinalIgnoreCase)',
                errors,
            )
            self.assertIn(
                "tests/RunServicesVerification/InstallLinkingContinuationVerification.cs missing marker: "
                "Native support case should redact claim-code values after HTML decimal hash separators.",
                errors,
            )

    def test_verifier_fail_closes_untyped_native_support_or_rollback_action_drift(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == Path("tests/RunServicesVerification/InstallLinkingContinuationVerification.cs"):
                    markers = [
                        marker
                        for marker in markers
                        if marker
                        not in {
                            "Native support action sanitizer should not preserve native support intake without reporter-needed support state.",
                            "Native support action sanitizer should not preserve native rollback without rollback-specific support state.",
                        }
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "tests/RunServicesVerification/InstallLinkingContinuationVerification.cs missing marker: "
                "Native support action sanitizer should not preserve native support intake without reporter-needed support state.",
                errors,
            )
            self.assertIn(
                "tests/RunServicesVerification/InstallLinkingContinuationVerification.cs missing marker: "
                "Native support action sanitizer should not preserve native rollback without rollback-specific support state.",
                errors,
            )

    def test_verifier_fail_closes_app_local_fragment_callback_state_drift(self) -> None:
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
                        if marker != "QueryHelpers.ParseQuery(component[prefix.Length..])"
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Controllers/InstallLinkingController.cs missing marker: "
                "QueryHelpers.ParseQuery(component[prefix.Length..])",
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
                        if marker != 'Assert.Contains("state=desktop", decodedCallbackHref, StringComparison.Ordinal);'
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs missing marker: "
                'Assert.Contains("state=desktop", decodedCallbackHref, StringComparison.Ordinal);',
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
                        if marker != 'Assert.Contains("nonce=callback-proof", decodedCallbackHref, StringComparison.Ordinal);'
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Tests/InstallLinkingControllerBrowserCallbackTests.cs missing marker: "
                'Assert.Contains("nonce=callback-proof", decodedCallbackHref, StringComparison.Ordinal);',
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
                if item != "/home/access"
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
            self.assertIn("proof_routes missing canonical flagship route: /home/access", result.stderr)

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
                "published proof file desktop_native_claim_and_recovery has wrong routes:",
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
            proof["proof_routes"].append("/HOME/ACCESS")
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
                "/HOME/ACCESS",
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

    def test_verifier_fail_closes_missing_desktop_client_readiness_block(self) -> None:
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
            self.assertEqual(0, materialize.returncode, msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}")

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof.pop("desktop_client_readiness", None)
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
            self.assertIn("missing desktop_client_readiness block", result.stderr)

    def test_verifier_fail_closes_desktop_client_readiness_drift_from_flagship_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            readiness_path = Path(temp_root) / "FLAGSHIP_PRODUCT_READINESS.generated.json"
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
            self.assertEqual(0, materialize.returncode, msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}")

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            readiness = {
                "contract_name": "fleet.flagship_product_readiness",
                "generated_at": "2026-05-05T21:31:06Z",
                "status": "fail",
                "scoped_status": "fail",
                "missing_keys": ["desktop_client"],
                "scoped_missing_keys": ["desktop_client"],
                "completion_audit": {
                    "status": "fail",
                    "reason": "desktop client proof is still blocked",
                },
                "flagship_readiness_audit": {
                    "reason": "desktop client proof is still blocked",
                },
            }
            readiness_path.write_text(json.dumps(readiness, indent=2) + "\n", encoding="utf-8")

            proof["desktop_client_readiness"]["reason"] = "drifted reason"
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
                    "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH": str(readiness_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("desktop_client_readiness has wrong reason", result.stderr)

    def test_runtime_projection_contracts_require_exact_fixed_schemas_and_types(self) -> None:
        verifier = load_verifier_module()
        canonical = json.loads(
            (REPO_ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json").read_text(
                encoding="utf-8"
            )
        )
        cases = [
            (
                "desktop extra key",
                lambda payload: payload["desktop_client_readiness"].__setitem__("unexpected", "value"),
                "desktop_client_readiness keys must be exactly",
            ),
            (
                "desktop wrong list type",
                lambda payload: payload["desktop_client_readiness"].__setitem__(
                    "missing_coverage_keys", "desktop_client"
                ),
                "desktop_client_readiness.missing_coverage_keys must be a list of strings",
            ),
            (
                "desktop wrong boolean type",
                lambda payload: payload["desktop_client_readiness"].__setitem__(
                    "desktop_client_missing", "false"
                ),
                "desktop_client_readiness.desktop_client_missing must be a boolean",
            ),
            (
                "release missing key",
                lambda payload: payload["release_channel"].pop("publishedAt"),
                "release_channel keys must be exactly",
            ),
            (
                "release wrong string type",
                lambda payload: payload["release_channel"].__setitem__("channelId", 7),
                "release_channel.channelId must be a string",
            ),
        ]

        for case_name, mutate, expected_error in cases:
            with self.subTest(case=case_name):
                payload = json.loads(json.dumps(canonical))
                mutate(payload)
                errors: list[str] = []
                verifier._verify_runtime_projection_contracts(errors, payload, "materialized proof file")
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    msg=f"expected {expected_error!r} in {errors!r}",
                )

    def test_release_channel_projection_statuses_require_canonical_binding_semantics(self) -> None:
        verifier = load_verifier_module()
        canonical = json.loads(
            (REPO_ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json").read_text(
                encoding="utf-8"
            )
        )

        complete_binding = {
            "status": "available",
            "path": "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json",
            "channelId": "preview",
            "channel": "preview",
            "version": "run-20260717-100000",
            "releaseVersion": "run-20260717-100000",
            "rolloutState": "review_required",
            "supportabilityState": "review_required",
            "publishedAt": "2026-07-17T10:00:00Z",
        }
        cases = [
            (
                "unknown status",
                {**complete_binding, "status": "published"},
                "release_channel.status must be available, unavailable, or invalid",
            ),
            (
                "available partial binding",
                {**complete_binding, "releaseVersion": ""},
                "available release_channel must publish one complete canonical binding",
            ),
            (
                "available naive timestamp",
                {**complete_binding, "publishedAt": "2026-07-17T10:00:00"},
                "available release_channel must publish one complete canonical binding",
            ),
            (
                "unavailable partial binding",
                {**complete_binding, "status": "unavailable"},
                "unavailable release_channel must not publish partial binding values",
            ),
            (
                "invalid complete binding",
                {**complete_binding, "status": "invalid"},
                "invalid release_channel must not contain a complete canonical binding",
            ),
        ]

        for case_name, release_channel, expected_error in cases:
            with self.subTest(case=case_name):
                payload = json.loads(json.dumps(canonical))
                payload["release_channel"] = release_channel
                errors: list[str] = []
                verifier._verify_runtime_projection_contracts(errors, payload, "served release proof file")
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    msg=f"expected {expected_error!r} in {errors!r}",
                )

        valid_payload = json.loads(json.dumps(canonical))
        valid_payload["release_channel"] = complete_binding
        valid_errors: list[str] = []
        verifier._verify_runtime_projection_contracts(
            valid_errors, valid_payload, "materialized proof file"
        )
        self.assertEqual([], valid_errors)

    def test_stable_payload_schema_normalizes_both_runtime_projections(self) -> None:
        verifier = load_verifier_module()
        canonical = json.loads(
            (REPO_ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as temp_root:
            first_path = Path(temp_root) / "published.json"
            second_path = Path(temp_root) / "materialized.json"
            first = json.loads(json.dumps(canonical))
            second = json.loads(json.dumps(canonical))
            second["desktop_client_readiness"]["generated_at"] = "2099-01-01T00:00:00Z"
            second["desktop_client_readiness"]["reason"] = "runtime readiness changed"
            second["release_channel"]["path"] = "runtime/RELEASE_CHANNEL.generated.json"
            first_path.write_text(json.dumps(first), encoding="utf-8")
            second_path.write_text(json.dumps(second), encoding="utf-8")

            errors: list[str] = []
            first_exact = verifier._stable_json_payload(first_path, errors, "published proof file")
            second_exact = verifier._stable_json_payload(second_path, errors, "served release proof file")
            first_stable = verifier._stable_json_payload(
                first_path,
                errors,
                "published proof file",
                schema_normalize_runtime_projections=True,
            )
            second_stable = verifier._stable_json_payload(
                second_path,
                errors,
                "materialized proof file",
                schema_normalize_runtime_projections=True,
            )

        self.assertEqual([], errors)
        self.assertNotEqual(first_exact, second_exact)
        self.assertEqual(first_stable, second_stable)
        self.assertEqual(
            {
                "projection": "desktop_client_readiness",
                "keys": sorted(verifier.DESKTOP_CLIENT_READINESS_KEYS),
            },
            first_stable["desktop_client_readiness"],
        )
        self.assertEqual(
            {
                "projection": "release_channel",
                "keys": sorted(verifier.RELEASE_CHANNEL_PROJECTION_KEYS),
            },
            first_stable["release_channel"],
        )

    def test_served_release_channel_projection_drift_still_fails_parity(self) -> None:
        verifier = load_verifier_module()
        canonical = json.loads(
            (REPO_ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as temp_root:
            published_path = Path(temp_root) / "published.json"
            served_path = Path(temp_root) / "served.json"
            served = json.loads(json.dumps(canonical))
            served["release_channel"]["path"] = "served/RELEASE_CHANNEL.generated.json"
            published_path.write_text(json.dumps(canonical), encoding="utf-8")
            served_path.write_text(json.dumps(served), encoding="utf-8")

            errors: list[str] = []
            verifier._verify_served_proof_matches_published(
                errors, published_path, served_path
            )

        self.assertIn(
            "served HUB_LOCAL_RELEASE_PROOF.generated.json drifts from "
            "published HUB_LOCAL_RELEASE_PROOF.generated.json for "
            "next90-m102-hub-desktop-native-trust",
            errors,
        )

    def test_rematerialized_runtime_projection_is_semantically_validated(self) -> None:
        verifier = load_verifier_module()
        canonical_path = REPO_ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
        with tempfile.TemporaryDirectory() as temp_root:
            fake_repo_root = Path(temp_root)
            scripts_dir = fake_repo_root / "scripts"
            scripts_dir.mkdir()
            proof_path = fake_repo_root / "published.json"
            proof_path.write_text(canonical_path.read_text(encoding="utf-8"), encoding="utf-8")
            materializer_path = scripts_dir / "materialize_hub_local_release_proof.py"
            materializer_path.write_text(
                "\n".join(
                    [
                        "import json",
                        "import sys",
                        "from pathlib import Path",
                        f"payload = json.loads(Path({str(canonical_path)!r}).read_text(encoding='utf-8'))",
                        "payload['release_channel'].pop('publishedAt', None)",
                        "Path(sys.argv[1]).write_text(json.dumps(payload), encoding='utf-8')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            errors: list[str] = []
            verifier._verify_materialized_proof_reproducible(
                errors, fake_repo_root, proof_path
            )

        self.assertTrue(
            any(
                "materialized proof file release_channel keys must be exactly" in error
                for error in errors
            ),
            msg=errors,
        )


if __name__ == "__main__":
    unittest.main()
