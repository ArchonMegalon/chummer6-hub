#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


PACKAGE_ID = "next90-m102-hub-desktop-native-trust"
LANDED_COMMIT = "160af58f"
FRONTIER_ID = 2897065929

REQUIRED_SOURCE_MARKERS = {
    Path("Chummer.Run.Api/Controllers/InstallLinkingController.cs"): [
        '[HttpPost("continuation")]',
        "ResolveInstallationForGrant(request.InstallationId, request.AccessToken)",
        "DesktopInstallRail.BuildContinuationReceipt(releaseArtifact, manifest, recoveryMode: false)",
        "FallbackPosture: continuation?.FallbackPosture",
        "BuildNativeNextSafeAction(updateAvailable, leadSupportCase, continuation)",
        "ResolveSupportContinuationCases(installation, installSummary, receipt)",
        "InstalledBuildReceiptId: receipt?.ReceiptId",
        "SupportCases: supportCases",
        "NormalizeCallbackUri(installLinkCallbackUri)",
        "string.Equals(parsed.Scheme, \"chummer\", StringComparison.OrdinalIgnoreCase)",
        "string.Equals(parsed.Host, \"install-link\", StringComparison.OrdinalIgnoreCase)",
        "string.Equals(parsed.Host, \"127.0.0.1\", StringComparison.OrdinalIgnoreCase)",
        "string.Equals(parsed.Host, \"localhost\", StringComparison.OrdinalIgnoreCase)",
        "[\"installLinkTransport\"] = \"grant_callback\"",
    ],
    Path("Chummer.Run.Api/Services/DesktopInstallRail.cs"): [
        "Claim codes are a recovery fallback, not a browser redemption step.",
        "desktop app update lane",
        "previous installed copy",
        "Support follow-through stays on the same install rail",
    ],
    Path("Chummer.Run.Api/Services/Support/SupportCasePresentationService.cs"): [
        "BuildInstallReadiness(",
        "FixReadyOnLinkedInstall",
        "NeedsInstallUpdate",
        "Follow-up stays inside Account > Support and Devices & access for this signed-in install rail.",
    ],
    Path("Chummer.Run.Api/Controllers/PublicLandingController.cs"): [
        '"/downloads/install/{artifactId}/continue.json"',
        "DesktopInstallRail.BuildSupportHref(",
        "DesktopInstallRail.BuildContinuationReceipt(",
        "ResolveSupportIntakeRailFromQuery()",
    ],
    Path("Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml"): [
        "Automatic account linking is the default path. Use claim-code fallback only when Chummer explicitly says it is in recovery mode.",
        "Support follow-through stays on the same install rail",
    ],
    Path("Chummer.Run.Api/Views/Accounts/Account.cshtml"): [
        "The next safe action is still inside Chummer on the already-downloaded device.",
        "Only use the recovery code if that copy explicitly enters recovery mode.",
        "Claim, update, rollback, recovery, and support stay on this same account rail once the install is linked.",
        "Use Devices & access for relinking, guided update follow-through, and support closure on the same copy.",
        "instead of starting a fresh browser ritual.",
    ],
    Path("tests/RunServicesVerification/InstallLinkingContinuationVerification.cs"): [
        "ContinueClaimedInstall(",
        "response.FallbackPosture.Contains(\"Claim codes are a recovery fallback\"",
        "UpdateAvailable",
        "NeedsInstallUpdate",
        "response.SupportCases[0].InstalledBuildReceiptId",
        "Support follow-through should expose installed build version truth.",
        "Invalid desktop continuation grants should fail closed.",
    ],
    Path("scripts/ai/verify.sh"): [
        "python3 scripts/verify_desktop_native_trust_receipts.py",
    ],
}


REQUIRED_PROOF_RECEIPTS = {
    "desktop_native_claim_and_recovery": {
        "package_id": "next90-m102-hub-desktop-native-trust",
        "milestone_id": 102,
        "frontier_id": FRONTIER_ID,
        "summary": (
            "Claim and recovery continuation now have installer/app-native receipts: guided setup is the default, "
            "claim codes are recovery fallback only, and the claimed desktop app can call the grant-bound "
            "continuation endpoint without a browser redemption ritual."
        ),
        "surfaces": [
            "desktop_native_claim_and_recovery",
            "install_claim_restore_continue",
            "claimed_install_continuation",
        ],
        "routes": [
            "/downloads/install/avalonia-linux-x64-installer/continue.json",
            "/api/v1/install-linking/continuation",
            "/account/access",
        ],
    },
    "support_followthrough:install_truth": {
        "package_id": "next90-m102-hub-desktop-native-trust",
        "milestone_id": 102,
        "frontier_id": FRONTIER_ID,
        "summary": (
            "Support follow-through carries installed build, current release, channel, head, platform, fallback, "
            "update, and rollback truth on the same install rail used by the desktop client."
        ),
        "surfaces": [
            "support_followthrough:install_truth",
            "support_case_install_readiness",
            "desktop_update_rollback_recovery",
        ],
        "routes": [
            "/api/v1/install-linking/continuation",
            "/account/support",
            "/contact",
        ],
    },
}

REQUIRED_TOP_LEVEL_PROOF_ROUTES = [
    "/downloads/install/avalonia-linux-x64-installer/continue.json",
    "/api/v1/install-linking/continuation",
    "/account/access",
    "/account/support",
    "/contact",
]

REQUIRED_TOP_LEVEL_JOURNEYS = [
    "install_claim_restore_continue",
]


REQUIRED_CANONICAL_QUEUE_MARKERS = [
    "title: Unify claim, install, update, and support recovery into one desktop-native flow",
    "task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
    f"package_id: {PACKAGE_ID}",
    f"frontier_id: {FRONTIER_ID}",
    "milestone_id: 102",
    "wave: W6",
    "repo: chummer6-hub",
    "status: complete",
    f"landed_commit: {LANDED_COMMIT}",
]

REQUIRED_CANONICAL_REGISTRY_MARKERS = [
    "id: 102.1",
    "owner: chummer6-hub",
    "status: complete",
    f"landed_commit: {LANDED_COMMIT}",
    PACKAGE_ID,
    "desktop_native_claim_and_recovery",
    "support_followthrough:install_truth",
]

REQUIRED_CANONICAL_REGISTRY_LISTS = {
    "evidence": [
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InstallLinkingController.cs exposes /api/v1/install-linking/continuation for grant-bound claimed desktop installs with current release, update, rollback, and support continuation truth.",
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml and /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/Accounts/Account.cshtml make guided setup/app continuation the default and keep claim codes as recovery fallback only.",
        "/docker/chummercomplete/chummer.run-services/scripts/verify_desktop_native_trust_receipts.py fail-closes missing source markers and missing successor proof receipts for desktop_native_claim_and_recovery and support_followthrough:install_truth.",
        "/docker/chummercomplete/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json carries next90-m102-hub-desktop-native-trust proof receipts for /downloads/install/avalonia-linux-x64-installer/continue.json, /api/v1/install-linking/continuation, /account/access, /account/support, and /contact.",
        "/docker/chummercomplete/chummer.run-services commit e27f24c1 tightens desktop-native continuation fallback-posture proof so claimed installs return the same fallback posture used by download and support recovery.",
        "/docker/chummercomplete/chummer.run-services commit e578a519 tightens the completed M102 proof pin so future shards verify the closed package instead of repeating it.",
        "/docker/chummercomplete/chummer.run-services commit 9fcec2a0 fail-closes M102 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
        "/docker/chummercomplete/chummer.run-services commit 266d526b pins the M102 queue proof hardening commit so stale queue proof cannot keep the package green.",
        "/docker/chummercomplete/chummer.run-services commit 6ea510c8 pins the M102 telemetry guard proof evidence so future shards verify the latest closed-package guard.",
        "/docker/chummercomplete/chummer.run-services commit 7a825c73 pins the M102 desktop trust guard evidence into the verifier and unit guard.",
        "/docker/chummercomplete/chummer.run-services commit aff39474 pins the M102 desktop trust latest guard.",
        "/docker/chummercomplete/chummer.run-services commit 38d50742 pins the M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit b9404a4c pins the M102 desktop trust latest proof guard.",
        "/docker/chummercomplete/chummer.run-services commit e6ae11a7 pins the M102 desktop trust guard closure.",
        "/docker/chummercomplete/chummer.run-services commit 4c542b50 pins the latest M102 desktop trust closure guard.",
        "/docker/chummercomplete/chummer.run-services commit 02bed909 pins the M102 desktop trust closure guard.",
        "/docker/chummercomplete/chummer.run-services commit 2017cdfe requires the latest M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 24432002 tightens the current M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 4afd6c3e pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit d99d080e pins the M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit b5b25e98 tightens M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit d7cb9d6e pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit ec81b660 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer.run-services commit b2d5cbfc tightens M102 generated proof hygiene.",
        "/docker/chummercomplete/chummer.run-services commit 5eac0f47 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 91514d42 pins M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit f7031d74 pins M102 desktop trust guard floor.",
        "/docker/chummercomplete/chummer.run-services commit f169b4a0 requires the current M102 desktop trust guard.",
        "/docker/chummercomplete/chummer.run-services commit b473e033 pins the current M102 desktop trust guard.",
        "/docker/chummercomplete/chummer.run-services commit 782fa007 requires the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 26817b22 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 6cf10549 pins M102 desktop trust 268 proof floor.",
        "/docker/chummercomplete/chummer.run-services commit de9653ee pins M102 desktop trust latest proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 3760ef63 tightens M102 active-run proof marker matching so queue, registry, and generated proof evidence reject helper references regardless of casing.",
        "/docker/chummercomplete/chummer.run-services commit 0337eeb5 pins the M102 active-run casing proof guard.",
        "/docker/chummercomplete/chummer.run-services commit ad21e50f pins the M102 active-run casing proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 51c46e74 pins the M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit ed3989d9 pins the M102 desktop trust proof floor guard.",
        "/docker/chummercomplete/chummer.run-services commit 653b23f0 tightens M102 desktop trust proof floor guard.",
        "/docker/chummercomplete/chummer.run-services commit 1a1c5615 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer.run-services commit ed689925 pins M102 desktop trust latest proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 461e3709 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 171c2de0 tightens M102 blocked run-helper proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 73f1ee9a pins M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 74dff34c tightens M102 forbidden command evidence guard.",
        "/docker/chummercomplete/chummer.run-services commit aea02326 pins the M102 forbidden command proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 2330a11c pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 99a03a04 pins the M102 current desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 0dca4b42 pins the M102 landed proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 2c351c92 pins M102 landed proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 575daa11 pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit bffcad4d tightens M102 proof timestamp stability so generatedAt-only proof refreshes do not reopen the closed desktop-native trust package.",
        "/docker/chummercomplete/chummer.run-services commit 9454feb7 pins M102 timestamp proof floor.",
        "/docker/chummercomplete/chummer.run-services commit f1513793 pins M102 timestamp proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 7ddbc973 pins M102 current proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 01800bd9 pins M102 current desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit c9bbf63c tightens M102 served proof shelf route guard.",
        "/docker/chummercomplete/chummer.run-services commit 2f7ed420 tightens M102 duplicate package-row proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 15c5f0e5 tightens M102 generated proof uniqueness so duplicate package or receipt rows fail closed.",
        "/docker/chummercomplete/chummer.run-services commit a270dcd0 tightens M102 desktop callback proof so app-local install-link callbacks cannot drift back to browser-only continuation.",
        "/docker/chummercomplete/chummer.run-services commit 4fa19f0c pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 6f468ee9 tightens M102 worker-state proof guard so run-state helper output cannot close desktop-native trust evidence.",
        "python3 scripts/verify_desktop_native_trust_receipts.py and python3 -m unittest tests/test_desktop_native_trust_receipts.py exit 0.",
        'dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "DesktopInstallRailTests|PublicLandingClaimRecoveryFlowTests|InstallLinkingContinuationVerification" --no-restore exits 0 for net10.0 and net10.0-windows.',
    ],
}

REQUIRED_CANONICAL_QUEUE_LISTS = {
    "proof": [
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InstallLinkingController.cs",
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/DesktopInstallRail.cs",
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/Support/SupportCasePresentationService.cs",
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml",
        "/docker/chummercomplete/chummer.run-services/scripts/verify_desktop_native_trust_receipts.py",
        "/docker/chummercomplete/chummer.run-services/tests/test_desktop_native_trust_receipts.py",
        "/docker/chummercomplete/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
        "/docker/chummercomplete/chummer.run-services commit e27f24c1 tightens desktop-native continuation fallback-posture proof.",
        "/docker/chummercomplete/chummer.run-services commit e578a519 tightens the completed M102 proof pin.",
        "/docker/chummercomplete/chummer.run-services commit 9fcec2a0 fail-closes M102 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
        "/docker/chummercomplete/chummer.run-services commit 266d526b pins the M102 queue proof hardening commit.",
        "/docker/chummercomplete/chummer.run-services commit 6ea510c8 pins the M102 telemetry guard proof evidence.",
        "/docker/chummercomplete/chummer.run-services commit 7a825c73 pins the M102 desktop trust guard evidence.",
        "/docker/chummercomplete/chummer.run-services commit aff39474 pins the M102 desktop trust latest guard.",
        "/docker/chummercomplete/chummer.run-services commit 38d50742 pins the M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit b9404a4c pins the M102 desktop trust latest proof guard.",
        "/docker/chummercomplete/chummer.run-services commit e6ae11a7 pins the M102 desktop trust guard closure.",
        "/docker/chummercomplete/chummer.run-services commit 4c542b50 pins the latest M102 desktop trust closure guard.",
        "/docker/chummercomplete/chummer.run-services commit 02bed909 pins the M102 desktop trust closure guard.",
        "/docker/chummercomplete/chummer.run-services commit 2017cdfe requires the latest M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 24432002 tightens the current M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 4afd6c3e pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit d99d080e pins the M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit b5b25e98 tightens M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit d7cb9d6e pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit ec81b660 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer.run-services commit b2d5cbfc tightens M102 generated proof hygiene.",
        "/docker/chummercomplete/chummer.run-services commit 5eac0f47 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 91514d42 pins M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit f7031d74 pins M102 desktop trust guard floor.",
        "/docker/chummercomplete/chummer.run-services commit f169b4a0 requires the current M102 desktop trust guard.",
        "/docker/chummercomplete/chummer.run-services commit b473e033 pins the current M102 desktop trust guard.",
        "/docker/chummercomplete/chummer.run-services commit 782fa007 requires the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 26817b22 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 6cf10549 pins M102 desktop trust 268 proof floor.",
        "/docker/chummercomplete/chummer.run-services commit de9653ee pins M102 desktop trust latest proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 3760ef63 tightens M102 active-run proof marker matching so queue, registry, and generated proof evidence reject helper references regardless of casing.",
        "/docker/chummercomplete/chummer.run-services commit 0337eeb5 pins the M102 active-run casing proof guard.",
        "/docker/chummercomplete/chummer.run-services commit ad21e50f pins the M102 active-run casing proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 51c46e74 pins the M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit ed3989d9 pins the M102 desktop trust proof floor guard.",
        "/docker/chummercomplete/chummer.run-services commit 653b23f0 tightens M102 desktop trust proof floor guard.",
        "/docker/chummercomplete/chummer.run-services commit 1a1c5615 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer.run-services commit ed689925 pins M102 desktop trust latest proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 461e3709 pins M102 desktop trust current proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 171c2de0 tightens M102 blocked run-helper proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 73f1ee9a pins M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 74dff34c tightens M102 forbidden command evidence guard.",
        "/docker/chummercomplete/chummer.run-services commit aea02326 pins the M102 forbidden command proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 2330a11c pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 99a03a04 pins the M102 current desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 0dca4b42 pins the M102 landed proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 2c351c92 pins M102 landed proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 575daa11 pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit bffcad4d tightens M102 proof timestamp stability so generatedAt-only proof refreshes do not reopen the closed desktop-native trust package.",
        "/docker/chummercomplete/chummer.run-services commit 9454feb7 pins M102 timestamp proof floor.",
        "/docker/chummercomplete/chummer.run-services commit f1513793 pins M102 timestamp proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 7ddbc973 pins M102 current proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 01800bd9 pins M102 current desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit c9bbf63c tightens M102 served proof shelf route guard.",
        "/docker/chummercomplete/chummer.run-services commit 2f7ed420 tightens M102 duplicate package-row proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 15c5f0e5 tightens M102 generated proof uniqueness so duplicate package or receipt rows fail closed.",
        "/docker/chummercomplete/chummer.run-services commit a270dcd0 tightens M102 desktop callback proof so app-local install-link callbacks cannot drift back to browser-only continuation.",
        "/docker/chummercomplete/chummer.run-services commit 4fa19f0c pins M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit 6f468ee9 tightens M102 worker-state proof guard so run-state helper output cannot close desktop-native trust evidence.",
        "python3 scripts/verify_desktop_native_trust_receipts.py",
        "python3 -m unittest tests/test_desktop_native_trust_receipts.py",
        'dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "DesktopInstallRailTests|PublicLandingClaimRecoveryFlowTests|InstallLinkingContinuationVerification" --no-restore',
    ],
    "allowed_paths": [
        "Chummer.Run.Api",
        "scripts",
        "tests",
    ],
    "owned_surfaces": [
        "desktop_native_claim_and_recovery",
        "support_followthrough:install_truth",
    ],
}

FORBIDDEN_PROOF_MARKERS = [
    "/var/lib/codex-fleet",
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "active-run helper",
    "active-run helper command",
    "active-run helper commands",
    "operator telemetry",
    "supervisor status",
    "status query",
    "status_query_supported",
    "polling_disabled",
    "polling disabled",
    "run_ooda_design_supervisor_until_quiet",
    "ooda_design_supervisor.py",
    "operator/OODA loop",
    "design_supervisor_ooda",
]
FORBIDDEN_PROOF_MARKER_MATCHES = [
    (marker, marker.casefold())
    for marker in FORBIDDEN_PROOF_MARKERS
]

REQUIRED_PROOF_PACKAGE = {
    "package_id": PACKAGE_ID,
    "milestone_id": 102,
    "frontier_id": FRONTIER_ID,
    "status": "complete",
    "landed_commit": LANDED_COMMIT,
    "title": "Unify claim, install, update, and support recovery into one desktop-native flow",
    "allowed_paths": REQUIRED_CANONICAL_QUEUE_LISTS["allowed_paths"],
    "owned_surfaces": REQUIRED_CANONICAL_QUEUE_LISTS["owned_surfaces"],
    "exit_criterion": "Claim, update, rollback, recovery, and support followthrough happen from the installer or app, not as browser ritual.",
}

REQUIRED_RESOLVING_COMMITS = [
    LANDED_COMMIT,
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
]

DEFAULT_PROOF_PATH = Path(".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json")
DEFAULT_SERVED_PROOF_PATH = Path("Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json")
DEFAULT_QUEUE_STAGING_PATH = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
DEFAULT_DESIGN_QUEUE_STAGING_PATH = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
DEFAULT_SUCCESSOR_REGISTRY_PATH = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml")
ABSOLUTE_REPO_PREFIX = "/docker/chummercomplete/chummer.run-services/"
MATERIALIZER_ARGS = [
    "https://chummer.run",
    "docker-compose.yml",
    "120",
    "true",
]
COMMIT_PROOF_RE = re.compile(r"\bcommit\s+([0-9a-f]{8,40})\b", re.IGNORECASE)


def _configured_path(env_name: str, default_path: Path) -> Path:
    override = os.environ.get(env_name)
    return Path(override) if override else default_path


def _configured_repo_anchor_root(repo_root: Path) -> Path:
    override = os.environ.get("CHUMMER_RUN_SERVICES_PROOF_ANCHOR_ROOT")
    return Path(override) if override else repo_root


def _proof_path(repo_root: Path) -> Path:
    configured = _configured_path("CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH", DEFAULT_PROOF_PATH)
    return configured if configured.is_absolute() else repo_root / configured


def _served_proof_path(repo_root: Path) -> Path:
    configured = _configured_path("CHUMMER_HUB_SERVED_RELEASE_PROOF_PATH", DEFAULT_SERVED_PROOF_PATH)
    return configured if configured.is_absolute() else repo_root / configured


def _extract_yaml_block(text: str, anchor: str) -> str | None:
    anchor_index = text.find(anchor)
    if anchor_index < 0:
        return None

    item_start = text.rfind("\n  - ", 0, anchor_index)
    start = anchor_index if item_start < 0 else item_start + 1
    next_item = text.find("\n  - ", start + 1)
    return text[start:] if next_item < 0 else text[start:next_item]


def _verify_marker_block(
    errors: list[str],
    path: Path,
    anchor: str,
    markers: list[str],
    label: str,
    required_lists: dict[str, list[str]] | None = None,
    forbidden_markers: list[str] | None = None,
) -> None:
    if not path.is_file():
        errors.append(f"missing canonical {label} file: {path}")
        return

    text = path.read_text(encoding="utf-8")
    block = _extract_yaml_block(text, anchor)
    if block is None:
        errors.append(f"canonical {label} missing block anchored by: {anchor}")
        return

    for marker in markers:
        if marker not in block:
            errors.append(f"canonical {label} block missing marker: {marker}")

    if forbidden_markers is not None:
        block_folded = block.casefold()
        marker_matches = (
            FORBIDDEN_PROOF_MARKER_MATCHES
            if forbidden_markers == FORBIDDEN_PROOF_MARKERS
            else [(marker, marker.casefold()) for marker in forbidden_markers]
        )
        for marker, marker_folded in marker_matches:
            if marker_folded in block_folded:
                errors.append(f"canonical {label} block has forbidden active-run proof marker: {marker}")

    if required_lists is not None:
        for key, expected_values in required_lists.items():
            actual_values = _extract_yaml_string_list(block, key)
            if actual_values is None:
                errors.append(f"canonical {label} block missing list: {key}")
                continue

            if actual_values != expected_values:
                errors.append(
                    f"canonical {label} block has wrong {key}: "
                    f"expected {expected_values!r}, got {actual_values!r}"
                )


def _verify_unique_yaml_anchor(errors: list[str], path: Path, anchor: str, label: str) -> None:
    if not path.is_file():
        return

    text = path.read_text(encoding="utf-8")
    count = sum(
        1
        for line in text.splitlines()
        if line.strip() == anchor or line.strip() == f"- {anchor}"
    )
    if count != 1:
        errors.append(f"canonical {label} has {count} rows anchored by: {anchor}")


def _extract_yaml_string_list(block: str, key: str) -> list[str] | None:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != f"{key}:":
            continue

        values: list[str] = []
        list_indent: int | None = None
        for child in lines[index + 1 :]:
            stripped = child.strip()
            if not stripped:
                continue

            indent = len(child) - len(child.lstrip(" "))
            if list_indent is None:
                list_indent = indent
            elif indent < list_indent:
                break

            if not stripped.startswith("- "):
                break

            values.append(stripped[2:].strip())

        return values

    return None


def _repo_anchor_from_proof_text(value: str) -> Path | None:
    if not value.startswith(ABSOLUTE_REPO_PREFIX):
        return None

    relative = value[len(ABSOLUTE_REPO_PREFIX) :].split(" ", 1)[0].strip()
    return Path(relative) if relative else None


def _required_repo_anchor_paths() -> list[Path]:
    anchors: list[Path] = []
    for values in (
        REQUIRED_CANONICAL_QUEUE_LISTS["proof"],
        REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"],
    ):
        for value in values:
            anchor = _repo_anchor_from_proof_text(value)
            if anchor is not None and anchor not in anchors:
                anchors.append(anchor)

    return anchors


def _verify_required_repo_anchor_paths(errors: list[str], repo_root: Path) -> None:
    anchor_root = _configured_repo_anchor_root(repo_root)
    for relative_path in _required_repo_anchor_paths():
        if not (anchor_root / relative_path).exists():
            errors.append(f"canonical proof anchor does not resolve: {ABSOLUTE_REPO_PREFIX}{relative_path}")


def _required_resolving_commits() -> list[str]:
    commits = list(REQUIRED_RESOLVING_COMMITS)
    extra_commits = os.environ.get("CHUMMER_DESKTOP_NATIVE_TRUST_EXTRA_REQUIRED_COMMITS", "")
    for commit in extra_commits.split(","):
        commit = commit.strip()
        if commit and commit not in commits:
            commits.append(commit)

    return commits


def _extract_proof_commit_ids(values: list[str]) -> set[str]:
    commit_ids: set[str] = set()
    for value in values:
        match = COMMIT_PROOF_RE.search(value)
        if match is not None:
            commit_ids.add(match.group(1).lower())

    return commit_ids


def _verify_canonical_commit_floor_consistency(errors: list[str]) -> None:
    queue_commits = _extract_proof_commit_ids(REQUIRED_CANONICAL_QUEUE_LISTS["proof"])
    registry_commits = _extract_proof_commit_ids(REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"])
    required_commits = {commit.lower() for commit in REQUIRED_RESOLVING_COMMITS}

    if queue_commits != registry_commits:
        errors.append(
            "M102 canonical queue and registry proof commit floors differ: "
            f"queue={sorted(queue_commits)!r}, registry={sorted(registry_commits)!r}"
        )

    for commit in sorted(queue_commits | registry_commits):
        if commit not in required_commits:
            errors.append(f"M102 canonical proof cites commit not enforced by resolver: {commit}")


def _verify_required_commits(errors: list[str], repo_root: Path) -> None:
    for commit in _required_resolving_commits():
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append(f"required M102 desktop-native trust proof commit does not resolve: {commit}")


def _verify_required_source_markers(errors: list[str], repo_root: Path) -> None:
    for relative_path, markers in REQUIRED_SOURCE_MARKERS.items():
        path = repo_root / relative_path
        if not path.is_file():
            errors.append(f"missing source file: {relative_path}")
            continue

        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                errors.append(f"{relative_path} missing marker: {marker}")


def _stable_json_payload(path: Path, errors: list[str], label: str) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{label} is not valid json: {exc}")
        return None

    if not isinstance(payload, dict):
        errors.append(f"{label} is not a json object")
        return None

    stable = dict(payload)
    stable.pop("generatedAt", None)
    stable.pop("generated_at", None)
    return stable


def _verify_json_has_no_forbidden_markers(
    errors: list[str],
    value: object,
    label: str,
    path: str = "$",
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _verify_json_has_no_forbidden_markers(errors, child, label, f"{path}.{key}")
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            _verify_json_has_no_forbidden_markers(errors, child, label, f"{path}[{index}]")
        return

    if not isinstance(value, str):
        return

    folded_value = value.casefold()
    for marker, marker_folded in FORBIDDEN_PROOF_MARKER_MATCHES:
        if marker_folded in folded_value:
            errors.append(f"{label} has forbidden active-run proof marker at {path}: {marker}")


def _verify_materialized_proof_reproducible(errors: list[str], repo_root: Path, proof_path: Path) -> None:
    materializer_path = repo_root / "scripts" / "materialize_hub_local_release_proof.py"
    if not materializer_path.is_file():
        errors.append("missing proof materializer: scripts/materialize_hub_local_release_proof.py")
        return

    published = _stable_json_payload(proof_path, errors, "published proof file")
    if published is None:
        return

    with tempfile.TemporaryDirectory() as temp_root:
        expected_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
        result = subprocess.run(
            ["python3", str(materializer_path), str(expected_path), *MATERIALIZER_ARGS],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append(
                "proof materializer failed while checking reproducibility: "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            )
            return

        expected = _stable_json_payload(expected_path, errors, "materialized proof file")
        if expected is None:
            return

    if published != expected:
        errors.append(
            "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from "
            "scripts/materialize_hub_local_release_proof.py for next90-m102-hub-desktop-native-trust"
        )


def _verify_unique_string_list(errors: list[str], values: list, label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue

        normalized = value.strip().casefold()
        if not normalized:
            continue

        if normalized in seen:
            duplicates.add(value.strip())
        else:
            seen.add(normalized)

    if duplicates:
        errors.append(f"{label} has duplicate entries: {', '.join(sorted(duplicates))}")


def _verify_m102_proof_payload(errors: list[str], proof: dict, label: str) -> None:
    _verify_json_has_no_forbidden_markers(errors, proof, label)

    proof_routes = proof.get("proof_routes")
    if not isinstance(proof_routes, list):
        errors.append(f"{label} missing list field: proof_routes")
    else:
        _verify_unique_string_list(errors, proof_routes, f"{label} proof_routes")
        proof_route_set = {item for item in proof_routes if isinstance(item, str)}
        for required in REQUIRED_TOP_LEVEL_PROOF_ROUTES:
            if required not in proof_route_set:
                errors.append(f"{label} proof_routes missing M102 route: {required}")

    journeys_passed = proof.get("journeys_passed")
    if not isinstance(journeys_passed, list):
        errors.append(f"{label} missing list field: journeys_passed")
    else:
        _verify_unique_string_list(errors, journeys_passed, f"{label} journeys_passed")
        journey_set = {item for item in journeys_passed if isinstance(item, str)}
        for required in REQUIRED_TOP_LEVEL_JOURNEYS:
            if required not in journey_set:
                errors.append(f"{label} journeys_passed missing M102 journey: {required}")

    packages = proof.get("successor_queue_packages")
    proof_package = None
    if isinstance(packages, list):
        matching_packages = [
            item
            for item in packages
            if isinstance(item, dict)
            and item.get("package_id") == PACKAGE_ID
        ]
        if len(matching_packages) != 1:
            errors.append(
                f"{label} has {len(matching_packages)} successor_queue_packages entries for {PACKAGE_ID}"
            )
        proof_package = matching_packages[0] if matching_packages else None

    if not isinstance(proof_package, dict):
        errors.append(f"{label} missing successor_queue_packages entry for next90-m102-hub-desktop-native-trust")
    else:
        for key, expected in REQUIRED_PROOF_PACKAGE.items():
            actual = proof_package.get(key)
            if actual != expected:
                errors.append(f"{label} proof package has wrong {key}: expected {expected!r}, got {actual!r}")

    receipt_items = proof.get("proof_receipts", [])
    if not isinstance(receipt_items, list):
        errors.append(f"{label} missing list field: proof_receipts")
        receipt_items = []

    receipts: dict[str, dict] = {}
    for receipt_id in REQUIRED_PROOF_RECEIPTS:
        matching_receipts = [
            item
            for item in receipt_items
            if isinstance(item, dict)
            and item.get("receipt_id") == receipt_id
        ]
        if len(matching_receipts) != 1:
            errors.append(f"{label} has {len(matching_receipts)} proof_receipts entries for {receipt_id}")
        if matching_receipts:
            receipts[receipt_id] = matching_receipts[0]

    for receipt_id, expected in REQUIRED_PROOF_RECEIPTS.items():
        receipt = receipts.get(receipt_id)
        if not isinstance(receipt, dict):
            errors.append(f"{label} missing receipt: {receipt_id}")
            continue

        for key in ("package_id", "milestone_id", "frontier_id", "summary"):
            if receipt.get(key) != expected[key]:
                errors.append(f"{label} {receipt_id} has wrong {key}: {receipt.get(key)!r}")

        for key in ("surfaces", "routes"):
            actual_values = receipt.get(key)
            if not isinstance(actual_values, list):
                errors.append(f"{label} {receipt_id} missing list field: {key}")
                continue

            _verify_unique_string_list(errors, actual_values, f"{label} {receipt_id} {key}")
            actual = {item for item in actual_values if isinstance(item, str)}
            for required in expected[key]:
                if required not in actual:
                    errors.append(f"{label} {receipt_id} missing {key[:-1]}: {required}")


def _verify_static_proof_file(errors: list[str], path: Path, label: str) -> None:
    if not path.is_file():
        errors.append(f"missing {label}: {path}")
        return

    try:
        proof = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{label} is not valid json: {exc}")
        return

    if not isinstance(proof, dict):
        errors.append(f"{label} is not a json object")
        return

    _verify_m102_proof_payload(errors, proof, label)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    errors: list[str] = []

    _verify_required_repo_anchor_paths(errors, repo_root)
    _verify_required_commits(errors, repo_root)
    _verify_canonical_commit_floor_consistency(errors)
    _verify_required_source_markers(errors, repo_root)

    proof_path = _proof_path(repo_root)
    if not proof_path.is_file():
        try:
            display_path = proof_path.relative_to(repo_root)
        except ValueError:
            display_path = proof_path
        errors.append(f"missing proof file: {display_path}")
    else:
        _verify_materialized_proof_reproducible(errors, repo_root, proof_path)
        try:
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"proof file is not valid json: {exc}")
        else:
            _verify_m102_proof_payload(errors, proof, "published proof file")

    _verify_static_proof_file(errors, _served_proof_path(repo_root), "served release proof file")

    queue_staging_path = _configured_path("CHUMMER_NEXT90_QUEUE_STAGING_PATH", DEFAULT_QUEUE_STAGING_PATH)
    design_queue_staging_path = _configured_path("CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH", DEFAULT_DESIGN_QUEUE_STAGING_PATH)
    successor_registry_path = _configured_path("CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH", DEFAULT_SUCCESSOR_REGISTRY_PATH)

    _verify_unique_yaml_anchor(errors, queue_staging_path, f"package_id: {PACKAGE_ID}", "successor queue staging")
    _verify_unique_yaml_anchor(errors, design_queue_staging_path, f"package_id: {PACKAGE_ID}", "design successor queue staging")
    _verify_unique_yaml_anchor(errors, successor_registry_path, "id: 102.1", "successor registry")

    _verify_marker_block(
        errors,
        queue_staging_path,
        f"package_id: {PACKAGE_ID}",
        REQUIRED_CANONICAL_QUEUE_MARKERS,
        "successor queue staging",
        REQUIRED_CANONICAL_QUEUE_LISTS,
        FORBIDDEN_PROOF_MARKERS,
    )
    _verify_marker_block(
        errors,
        design_queue_staging_path,
        f"package_id: {PACKAGE_ID}",
        REQUIRED_CANONICAL_QUEUE_MARKERS,
        "design successor queue staging",
        REQUIRED_CANONICAL_QUEUE_LISTS,
        FORBIDDEN_PROOF_MARKERS,
    )
    _verify_marker_block(
        errors,
        successor_registry_path,
        "id: 102.1",
        REQUIRED_CANONICAL_REGISTRY_MARKERS,
        "successor registry",
        REQUIRED_CANONICAL_REGISTRY_LISTS,
        FORBIDDEN_PROOF_MARKERS,
    )

    if errors:
        print("desktop native trust receipt verification failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("desktop native trust receipts verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
