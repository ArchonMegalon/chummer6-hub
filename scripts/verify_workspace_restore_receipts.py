#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_WORKSPACE_RESTORE_RECEIPTS_ROOT", DEFAULT_ROOT))
PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_WORKSPACE_RESTORE_RECEIPTS_PROOF",
        ROOT / ".codex-studio" / "published" / "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json",
    )
)
LOCAL_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_WORKSPACE_RESTORE_RECEIPTS_LOCAL_RELEASE_PROOF",
        ROOT / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json",
    )
)
SERVED_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_WORKSPACE_RESTORE_RECEIPTS_SERVED_RELEASE_PROOF",
        ROOT / "Chummer.Run.Api" / "wwwroot" / "proofs" / "mac-codex-release" / "HUB_LOCAL_RELEASE_PROOF.generated.json",
    )
)
REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_WORKSPACE_RESTORE_RECEIPTS_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_WORKSPACE_RESTORE_RECEIPTS_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
MATERIALIZER_PATH = ROOT / "scripts" / "materialize_hub_local_release_proof.py"
PACKAGE_ID = "next90-m105-hub-workspace-continuity"
PACKAGE_TASK = "Make roaming workspace, entitlement replication, stale state, and conflict posture explicit and recoverable."
LANDED_COMMIT = "4d4b3856"
FRONTIER_ID = 4623636482
MILESTONE_ID = 105
PACKAGE_REPO_ROOT = "/docker/chummercomplete/chummer.run-services/"
ALLOWED_PROOF_PATH_PREFIXES = (
    "Chummer.Run.Api/",
    "scripts/",
    "tests/",
)
DEFAULT_REQUIRED_LOCAL_COMMITS = [
    LANDED_COMMIT,
    "b39147dc",
    "5796e220",
    "80454b41",
    "e1f65c8b",
    "b72eaf89",
    "290ec61e",
    "1d11729a",
    "35db07af",
    "784fbcef",
    "5c8e5527",
    "bd398493",
    "a45d9e9e",
    "a002019a",
    "717af57e",
    "346c3ede",
    "8d59d95f",
    "1b8d9363",
    "e0521ca5",
    "06e2ec99",
    "cb560573",
    "7c92635e",
    "fcdd1fa5",
    "c90d02e0",
    "211ce4a1",
    "93182934",
    "021de48a",
    "5bf1a11e",
    "db002589",
    "f6db9d91",
    "b1270fd0",
    "691c625f",
    "f8226de9",
    "f8f3ce8e",
    "70b6f382",
    "0014a763",
    "d26e961c",
    "9f723c15",
    "7e908447",
    "2df21683",
    "442c76c2",
    "1f4f0e2e",
    "29f7ec9b",
    "46551461",
    "b4da7025",
    "af336c17",
    "aa61c498",
    "1b1c5427",
    "1d5a811f",
    "f02e985f",
    "0f06bcef",
    "1ca535e2",
    "25fb4391",
    "41c106c8",
    "b4bdc153",
    "1c98d6ba",
    "83bbc0d4",
    "1a0ba130",
    "63313972",
    "0b038324",
    "447f2a90",
    "a8f94a63",
    "06b0e574",
    "79764447",
    "2960fc91",
    "0f4a31d3",
    "d7788857",
    "8dcd8b46",
    "f5f414b0",
    "5e77a853",
    "23308c16",
    "2da59c68",
    "71e514b2",
    "e0d2bff6",
    "c6f628ef",
    "fa17ff4d",
    "72f96452",
    "664737cb",
    "138d84ef",
    "109face0",
    "28b9e40a",
    "f6cd760e",
    "03517936",
    "57da8fb3",
    "aa7d6b9a",
    "6add6cc6",
    "4487d01a",
    "9171e3f4",
    "a7e826d3",
    "d882db69",
    "db4fe453",
    "57a5b16d",
    "02596ecc",
    "a08ba77b",
    "9f425d04",
    "7c7a741a",
    "75dba18c",
    "f221ec3f",
    "39761fd0",
    "d00cf74c",
    "049e2938",
    "58edeea6",
    "586ad535",
    "54d3756f",
    "c6f0439e",
    "db056eb5",
    "19536ab1",
    "3eb87a75",
    "3b854764",
    "44bada17",
    "31b76424",
    "121f3571",
    "3d77bb73",
    "bbfe3722",
    "9d1fe095",
    "2f85eb13",
]
REQUIRED_LOCAL_COMMITS = [
    item.strip()
    for item in os.environ.get(
        "CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REQUIRED_COMMITS",
        ",".join(DEFAULT_REQUIRED_LOCAL_COMMITS),
    ).split(",")
    if item.strip()
]

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Campaign.Contracts/CampaignContracts.cs": [
        "public sealed record WorkspaceRestoreProvenanceReceipt(",
        "string Surface,",
        "string? Authority = null,",
        "string? RecoveryHint = null);",
        "public sealed record WorkspaceRestoreConflictReceipt(",
        "string? Surface = null,",
        "bool BlocksContinue = false);",
    ],
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs": [
        "Authority: \"hub_entitlement_ledger\"",
        "RecoveryHint: matchedInstallation",
        "Kind: \"entitlement_artifact_drift\"",
        "Surface: \"entitlement_sync\"",
        "BlocksContinue: true",
        "Kind: \"claimed_installation_stale\"",
        "Surface: \"workspace_restore\"",
    ],
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs": [
        "[HttpGet(\"me/restore\")]",
        "[ProducesResponseType<WorkspaceRestoreProjection>(StatusCodes.Status200OK)]",
        "GetMyRestoreProjection(CancellationToken cancellationToken)",
        "return Ok(_campaignSpine.GetRestoreProjection(user, installLinking));",
    ],
    "Chummer.Run.Api/Services/Community/WorkspaceLifecyclePolicyService.cs": [
        "ProvenanceReceipts = NormalizeReceiptObservations(candidate.ProvenanceReceipts, existing.ProvenanceReceipts)",
        "ConflictReceipts = NormalizeConflictObservations(candidate.ConflictReceipts, existing.ConflictReceipts)",
        "existingObservedById.TryGetValue(item.ReceiptId, out DateTimeOffset observedAtUtc)",
        "item with { ObservedAtUtc = observedAtUtc }",
    ],
    "Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs": [
        "RestoreProvenanceReceipts: ProjectRestoreProvenanceReceipts(context.Restore.ProvenanceReceipts)",
        "RestoreConflictReceipts: ProjectRestoreConflictReceipts(context.Restore.ConflictReceipts)",
        "ResolveRestoreReceiptSurface(receipt.Surface, receipt.Kind)",
        "Resolution: ResolveRestoreConflictResolution(receipt)",
        "Open account access and resolve this restore receipt before continuing on this workspace.",
        "IsEntitlementRestoreKind(kind)",
    ],
    "scripts/materialize_hub_local_release_proof.py": [
        '"package_id": "next90-m105-hub-workspace-continuity"',
        '"frontier_id": 4623636482',
        '"status": "complete"',
        '"landed_commit": "4d4b3856"',
        '"workspace_restore:provenance"',
        '"entitlement_sync:conflict_receipts"',
        '"Claimed users can restore workspace, entitlement, last context, and safe continuation with explicit stale and conflict posture."',
    ],
    "Chummer.Run.Api/Views/Accounts/Account.cshtml": [
        "Restore provenance and conflict receipts",
        "Authority: @HumanizeStatus(receipt.Authority, \"hub\")",
        "@receipt.RecoveryHint",
        "Continue is blocked until this receipt is resolved.",
    ],
    "tests/RunServicesSmoke/Program.cs": [
        "workspaceServerPlanePayload.RestoreProvenanceReceipts.Count == restorePayload!.ProvenanceReceipts.Count",
        "workspaceServerPlanePayload.RestoreConflictReceipts.Count == restorePayload.ConflictReceipts.Count",
        "string.Equals(item.Authority, \"hub_entitlement_ledger\", StringComparison.Ordinal)",
        "!string.IsNullOrWhiteSpace(item.RecoveryHint)",
        "string.Equals(item.Kind, \"entitlement_artifact_drift\", StringComparison.OrdinalIgnoreCase)",
        "item.BlocksContinue",
    ],
    "tests/RunServicesVerification/CampaignSpineRestoreVerification.cs": [
        "VerifyRestoreConflictReceiptsCaptureStaleClaimAndEntitlementState();",
        "VerifyRestoreReceiptsSurviveCommunityStoreReload();",
        "Restore projection should emit provenance receipts for entitlement, install, and rule-posture replay.",
        "Entitlement drift receipts should stay explicitly classified under entitlement sync and block continue until resolved.",
    ],
    "tests/RunServicesVerification/WorkspaceLifecycleRetentionVerification.cs": [
        "VerifyUnchangedRestoreProjectionPreservesReceiptObservationTimestamps();",
        "Unchanged restore projections should preserve provenance receipt observation timestamps.",
        "Unchanged restore projections should preserve conflict receipt observation timestamps.",
    ],
    "Chummer.Tests/WorkspaceLifecyclePolicyServiceTests.cs": [
        "FinalizeRestoreProjectionPreservesReceiptObservationTimestampsWhenContentIsUnchanged",
        "Assert.Equal(existing.ProvenanceReceipts![0].ObservedAtUtc.ToString(\"O\"), finalized.ProvenanceReceipts![0].ObservedAtUtc.ToString(\"O\"));",
        "Assert.Equal(existing.ConflictReceipts![0].ObservedAtUtc.ToString(\"O\"), finalized.ConflictReceipts![0].ObservedAtUtc.ToString(\"O\"));",
    ],
}

PROOF_MARKERS = [
    "workspaceServerPlanePayload.RestoreProvenanceReceipts.Count == restorePayload!.ProvenanceReceipts.Count",
    "workspaceServerPlanePayload.RestoreConflictReceipts.Count == restorePayload.ConflictReceipts.Count",
    "string.Equals(item.Authority, \"hub_entitlement_ledger\", StringComparison.Ordinal)",
    "!string.IsNullOrWhiteSpace(item.RecoveryHint)",
    "string.Equals(item.Kind, \"entitlement_artifact_drift\", StringComparison.OrdinalIgnoreCase)",
    "accountSource.Contains(\"Continue is blocked until this receipt is resolved.\"",
]

STANDARD_VERIFY_MARKERS = [
    "python3 scripts/verify_workspace_restore_receipts.py",
    "python3 -m unittest tests/test_workspace_restore_receipts.py tests/test_workspace_restore_queue_frontier_guard.py tests/test_workspace_restore_commit_resolution.py",
]

LOCAL_RELEASE_PROOF_RECEIPTS: dict[str, dict[str, object]] = {
    "workspace_restore:provenance": {
        "routes": ["/home/work", "/account/work"],
        "surfaces": [
            "workspace_restore:provenance",
            "workspace_restore",
            "account_workspace_detail",
        ],
        "summary_markers": [
            "claimed installs",
            "recent artifacts",
            "rule environments",
            "restore inventory",
        ],
    },
    "entitlement_sync:conflict_receipts": {
        "routes": ["/home/work", "/account/work"],
        "surfaces": [
            "entitlement_sync:conflict_receipts",
            "entitlement_sync",
            "workspace_restore",
        ],
        "summary_markers": [
            "Entitlement drift",
            "stale claims",
            "missing grants",
            "continue-blocking conflicts",
            "recoverable receipts",
        ],
    },
}

LOCAL_RELEASE_PROOF_PACKAGE: dict[str, object] = {
    "package_id": PACKAGE_ID,
    "milestone_id": MILESTONE_ID,
    "frontier_id": FRONTIER_ID,
    "status": "complete",
    "landed_commit": LANDED_COMMIT,
    "title": "Emit provenance and conflict receipts for workspace restore and continuity",
    "allowed_paths": [
        "Chummer.Run.Api",
        "scripts",
        "tests",
    ],
    "owned_surfaces": [
        "workspace_restore:provenance",
        "entitlement_sync:conflict_receipts",
    ],
    "exit_criterion": "Claimed users can restore workspace, entitlement, last context, and safe continuation with explicit stale and conflict posture.",
}

QUEUE_ALLOWED_PATHS = [
    "Chummer.Run.Api",
    "scripts",
    "tests",
]

QUEUE_OWNED_SURFACES = [
    "workspace_restore:provenance",
    "entitlement_sync:conflict_receipts",
]

REGISTRY_MARKERS = [
    "id: 105.1",
    "owner: chummer6-hub",
    "title: Emit provenance and conflict receipts for roaming workspace and entitlement replication.",
    "status: complete",
    f"landed_commit: {LANDED_COMMIT}",
    f"/docker/chummercomplete/chummer.run-services commit {LANDED_COMMIT} emits workspace_restore provenance receipts",
    "/docker/chummercomplete/chummer.run-services commit b39147dc tightens the workspace restore verifier so Hub local release proof must retain the next90-m105-hub-workspace-continuity package, frontier id 4623636482, /home/work and /account/work routes, and both workspace_restore:provenance and entitlement_sync:conflict_receipts receipts.",
    "/docker/chummercomplete/chummer.run-services commit 5796e220 wires the M105 workspace restore verifier into scripts/ai/verify.sh so standard Hub verification runs the closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 80454b41 fail-closes workspace restore proof if landed verifier commits no longer resolve locally.",
    "/docker/chummercomplete/chummer.run-services commit 1d11729a fail-closes M105 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
    "/docker/chummercomplete/chummer.run-services commit 784fbcef pins the M105 workspace continuity receipt materializer so regenerated local release proof cannot drop the closed package metadata, provenance receipts, or conflict receipts.",
    "/docker/chummercomplete/chummer.run-services commit a45d9e9e pins the M105 workspace guard closure so stale clones cannot satisfy completed-package proof without the latest local guard commits.",
    "/docker/chummercomplete/chummer.run-services commit a002019a pins the latest M105 workspace proof guard so future shards verify the closed successor package instead of repeating it.",
    "/docker/chummercomplete/chummer.run-services commit cb560573 requires the M105 queue proof floor so registry and queue closure cannot regress behind the latest completed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 7c92635e tightens the M105 workspace proof floor so future shards verify the current closed-package guard instead of repeating this completed slice.",
    "/docker/chummercomplete/chummer.run-services commit fcdd1fa5 pins the current M105 workspace proof floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 021de48a requires the current M105 queue proof guard so stale registry and queue evidence cannot keep the completed package green.",
    "/docker/chummercomplete/chummer.run-services commit 5bf1a11e pins the current M105 workspace queue guard so future shards verify the latest closed-package proof floor.",
    "/docker/chummercomplete/chummer.run-services commit db002589 pins the M105 workspace queue guard proof so future shards verify the current closed-package proof floor.",
    "/docker/chummercomplete/chummer.run-services commit f6db9d91 pins the M105 workspace proof floor after the queue guard proof tightening.",
    "/docker/chummercomplete/chummer.run-services commit b1270fd0 pins the M105 workspace verifier to the canonical f6db9d91 proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 691c625f requires the current M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit f8226de9 pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit f8f3ce8e requires the latest M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 70b6f382 tightens the M105 served workspace proof guard so public served receipts cannot drift from the local proof shelf.",
    "/docker/chummercomplete/chummer.run-services commit 0014a763 tightens the M105 active-run proof marker guard to reject forbidden helper evidence case-insensitively.",
    "/docker/chummercomplete/chummer.run-services commit d26e961c tightens the M105 workspace release proof guard so package metadata and receipt routes or surfaces must match the canonical closed-package receipt exactly.",
    "/docker/chummercomplete/chummer.run-services commit 9f723c15 tightens the M105 queue mirror guard so Fleet and design completed-package rows cannot drift while retaining required proof tokens.",
    "/docker/chummercomplete/chummer.run-services commit 7e908447 tightens the M105 workspace receipt proof so package-scoped release proof cannot widen beyond the canonical workspace_restore:provenance and entitlement_sync:conflict_receipts receipts.",
    "/docker/chummercomplete/chummer.run-services commit 2df21683 pins the M105 workspace receipt proof floor so future shards verify the latest closed-package guard instead of repeating it.",
    "/docker/chummercomplete/chummer.run-services commit 442c76c2 pins the M105 workspace receipt guard floor so canonical registry and queue proof must cite the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 1f4f0e2e requires the current M105 workspace receipt guard floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 29f7ec9b pins the M105 workspace receipt proof floor.",
    "/docker/chummercomplete/chummer.run-services commit b4da7025 pins the M105 workspace proof floor guard and rejects active-run handoff paths as queue proof.",
    "/docker/chummercomplete/chummer.run-services commit 46551461 tightens the M105 standard verify entrypoint guard so closed-package proof cannot rely on blocked run-helper references.",
    "/docker/chummercomplete/chummer.run-services commit 1b1c5427 pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit 1d5a811f pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit f02e985f tightens the M105 blocked-helper command guard so queue and registry proof cannot cite active-run OODA helper command output.",
    "/docker/chummercomplete/chummer.run-services commit 0f06bcef pins the M105 helper guard proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 1ca535e2 pins the M105 workspace helper proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 25fb4391 pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 41c106c8 pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit b4bdc153 pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit 1c98d6ba pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 83bbc0d4 tightens the M105 workspace duplicate proof guard.",
    "/docker/chummercomplete/chummer.run-services commit 1a0ba130 pins the M105 workspace duplicate proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 63313972 pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 0b038324 tightens M105 local and served release proof uniqueness so duplicate closed-package rows or duplicate package-scoped receipts cannot keep the package green.",
    "/docker/chummercomplete/chummer.run-services commit 447f2a90 pins the M105 workspace uniqueness proof floor so future shards verify the current closed-package guard instead of repeating it.",
    "/docker/chummercomplete/chummer.run-services commit a8f94a63 pins the M105 workspace uniqueness proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 06b0e574 pins the current M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit 79764447 pins the M105 workspace current proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 0f4a31d3 pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit d7788857 tightens the M105 workspace canonical proof floor.",
    "/docker/chummercomplete/chummer.run-services commit f5f414b0 pins the M105 workspace current proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 5e77a853 pins the M105 workspace current proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 23308c16 requires the current M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit 2da59c68 pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit 71e514b2 pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit e0d2bff6 pins the M105 workspace queue-frontier guard proof.",
    "/docker/chummercomplete/chummer.run-services commit c6f628ef pins the M105 verifier to the canonical queue-frontier proof floor.",
    "/docker/chummercomplete/chummer.run-services commit fa17ff4d tightens the M105 workspace queue task guard so completed-package proof must retain the exact assigned successor task text.",
    "/docker/chummercomplete/chummer.run-services commit 72f96452 pins the M105 workspace task guard proof.",
    "/docker/chummercomplete/chummer.run-services commit 664737cb pins the current M105 workspace task guard floor.",
    "/docker/chummercomplete/chummer.run-services commit 138d84ef pins the latest M105 workspace task guard floor.",
    "/docker/chummercomplete/chummer.run-services commit 109face0 pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 28b9e40a pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit f6cd760e tightens the M105 verifier to require the current queue-cited workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 03517936 tightens the M105 restore API proof guard so completed-package proof fails if /api/v1/campaign-spine/me/restore loses the workspace restore projection route.",
    "/docker/chummercomplete/chummer.run-services commit 57da8fb3 preserves workspace restore receipt observation timestamps for unchanged provenance and conflict receipts and pins the behavior in verifier proof.",
    "/docker/chummercomplete/chummer.run-services commit aa7d6b9a pins the M105 current workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 6add6cc6 pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 4487d01a pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit 9171e3f4 tightens M105 release proof receipt uniqueness so duplicate unscoped workspace or entitlement receipt ids cannot hide beside the closed package receipts.",
    "/docker/chummercomplete/chummer.run-services commit a7e826d3 pins the M105 workspace receipt uniqueness proof floor.",
    "/docker/chummercomplete/chummer.run-services commit d882db69 pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit db4fe453 tightens M105 served proof route mirroring so public proof shelves cannot drift from local route receipts.",
    "/docker/chummercomplete/chummer.run-services commit 57a5b16d tightens M105 proof commit citation resolution so every registry and queue commit proof citation must resolve locally.",
    "/docker/chummercomplete/chummer.run-services commit 02596ecc tightens M105 proof path scope so registry and queue proof paths must stay inside Chummer.Run.Api, scripts, or tests.",
    "/docker/chummercomplete/chummer.run-services commit a08ba77b tightens M105 embedded proof path scope so prose proof bullets cannot cite paths outside Chummer.Run.Api, scripts, or tests.",
    "/docker/chummercomplete/chummer.run-services commit 9f425d04 tightens M105 package-scoped receipt proof so untracked workspace continuity receipt rows cannot hide beside the canonical receipts.",
    "/docker/chummercomplete/chummer.run-services commit 75dba18c pins the current M105 workspace receipt test proof floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit f221ec3f tightens the M105 worker telemetry proof guard so completed-package evidence cannot cite control-plane helper output or worker-run telemetry summaries.",
    "/docker/chummercomplete/chummer.run-services commit 39761fd0 tightens the M105 successor telemetry proof guard so copied remaining-milestone, queue-item, or critical-path summaries cannot close the completed workspace package.",
    "/docker/chummercomplete/chummer.run-services commit d00cf74c tightens the M105 campaign OS proof guard so generated campaign proof cannot cite blocked run-control evidence.",
    "/docker/chummercomplete/chummer.run-services commit 049e2938 pins the M105 campaign proof guard.",
    "/docker/chummercomplete/chummer.run-services commit 58edeea6 tightens the M105 worker-context field guard so queue proof cannot cite task-local run context fields.",
    "/docker/chummercomplete/chummer.run-services commit 586ad535 tightens the M105 successor handoff proof guard so completed-package proof cannot cite copied handoff-context run fields.",
    "/docker/chummercomplete/chummer.run-services commit 54d3756f tightens the M105 successor prompt proof guard so copied successor frontier id, assigned package, and execution-rule fields cannot close the completed workspace package.",
    "/docker/chummercomplete/chummer.run-services commit c6f0439e pins the M105 successor handoff proof floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit db056eb5 pins the M105 successor prompt proof floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 19536ab1 pins the M105 workspace proof floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 3eb87a75 pins the M105 workspace proof floor guard so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 3b854764 tightens the M105 workspace queue scope guard so completed-package proof cannot widen allowed paths or owned surfaces.",
    "/docker/chummercomplete/chummer.run-services commit 44bada17 pins the M105 workspace queue scope proof so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 31b76424 tightens the M105 workspace materializer proof so committed release receipts must be reproducible from scripts/materialize_hub_local_release_proof.py.",
    "/docker/chummercomplete/chummer.run-services commit 121f3571 pins the M105 workspace materializer proof floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 3d77bb73 tightens the M105 active-run handoff transcript guard so copied prompt, model, and stderr-tail fields cannot close the completed workspace package.",
    "/docker/chummercomplete/chummer.run-services commit bbfe3722 tightens the M105 package receipt metadata guard so wrong-frontier package receipts cannot sit beside the closed workspace continuity receipts.",
    "/docker/chummercomplete/chummer.run-services commit 9d1fe095 tightens the M105 release-proof package mirror guard so top-level and package-list closure metadata cannot drift.",
    "/docker/chummercomplete/chummer.run-services commit 2f85eb13 hardens M105 restore conflict recovery receipts so blocking server-plane conflicts keep an actionable resolution fallback.",
    "/docker/chummercomplete/chummer.run-services/scripts/verify_workspace_restore_receipts.py fail-closes missing source/proof markers",
    "/docker/chummercomplete/chummer.run-services/tests/test_workspace_restore_queue_frontier_guard.py",
    "python3 scripts/verify_workspace_restore_receipts.py exits 0.",
    "python3 -m unittest tests/test_workspace_restore_receipts.py exits 0.",
    "python3 -m unittest tests/test_workspace_restore_receipts.py tests/test_workspace_restore_queue_frontier_guard.py tests/test_workspace_restore_commit_resolution.py exits 0.",
    "dotnet test Chummer.Tests/Chummer.Tests.csproj --filter \"CampaignSpineRestoreReceiptTests|CampaignWorkspaceServerPlaneServiceTests|CampaignOsLocalProofMaterializerTests\" --no-restore exits 0",
]

QUEUE_STAGING_MARKERS = [
    "title: Emit provenance and conflict receipts for workspace restore and continuity",
    f"task: {PACKAGE_TASK}",
    f"package_id: {PACKAGE_ID}\n",
    f"frontier_id: {FRONTIER_ID}",
    "milestone_id: 105",
    "repo: chummer6-hub",
    "status: complete",
    f"landed_commit: {LANDED_COMMIT}",
    "/docker/chummercomplete/chummer.run-services commit 5796e220 wires the M105 workspace restore verifier into scripts/ai/verify.sh so standard Hub verification runs the closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 80454b41 fail-closes workspace restore proof if landed verifier commits no longer resolve locally.",
    "/docker/chummercomplete/chummer.run-services commit 1d11729a fail-closes M105 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
    "/docker/chummercomplete/chummer.run-services commit 784fbcef pins the M105 workspace continuity receipt materializer so regenerated local release proof cannot drop the closed package metadata, provenance receipts, or conflict receipts.",
    "/docker/chummercomplete/chummer.run-services commit a45d9e9e pins the M105 workspace guard closure so stale clones cannot satisfy completed-package proof without the latest local guard commits.",
    "/docker/chummercomplete/chummer.run-services commit a002019a pins the latest M105 workspace proof guard so future shards verify the closed successor package instead of repeating it.",
    "/docker/chummercomplete/chummer.run-services commit cb560573 requires the M105 queue proof floor so registry and queue closure cannot regress behind the latest completed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 7c92635e tightens the M105 workspace proof floor so future shards verify the current closed-package guard instead of repeating this completed slice.",
    "/docker/chummercomplete/chummer.run-services commit fcdd1fa5 pins the current M105 workspace proof floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 021de48a requires the current M105 queue proof guard so stale registry and queue evidence cannot keep the completed package green.",
    "/docker/chummercomplete/chummer.run-services commit 5bf1a11e pins the current M105 workspace queue guard so future shards verify the latest closed-package proof floor.",
    "/docker/chummercomplete/chummer.run-services commit db002589 pins the M105 workspace queue guard proof so future shards verify the current closed-package proof floor.",
    "/docker/chummercomplete/chummer.run-services commit f6db9d91 pins the M105 workspace proof floor after the queue guard proof tightening.",
    "/docker/chummercomplete/chummer.run-services commit b1270fd0 pins the M105 workspace verifier to the canonical f6db9d91 proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 691c625f requires the current M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit f8226de9 pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit f8f3ce8e requires the latest M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 70b6f382 tightens the M105 served workspace proof guard so public served receipts cannot drift from the local proof shelf.",
    "/docker/chummercomplete/chummer.run-services commit 0014a763 tightens the M105 active-run proof marker guard to reject forbidden helper evidence case-insensitively.",
    "/docker/chummercomplete/chummer.run-services commit d26e961c tightens the M105 workspace release proof guard so package metadata and receipt routes or surfaces must match the canonical closed-package receipt exactly.",
    "/docker/chummercomplete/chummer.run-services commit 9f723c15 tightens the M105 queue mirror guard so Fleet and design completed-package rows cannot drift while retaining required proof tokens.",
    "/docker/chummercomplete/chummer.run-services commit 7e908447 tightens the M105 workspace receipt proof so package-scoped release proof cannot widen beyond the canonical workspace_restore:provenance and entitlement_sync:conflict_receipts receipts.",
    "/docker/chummercomplete/chummer.run-services commit 2df21683 pins the M105 workspace receipt proof floor so future shards verify the latest closed-package guard instead of repeating it.",
    "/docker/chummercomplete/chummer.run-services commit 442c76c2 pins the M105 workspace receipt guard floor so canonical registry and queue proof must cite the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 1f4f0e2e requires the current M105 workspace receipt guard floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 29f7ec9b pins the M105 workspace receipt proof floor.",
    "/docker/chummercomplete/chummer.run-services commit b4da7025 pins the M105 workspace proof floor guard and rejects active-run handoff paths as queue proof.",
    "/docker/chummercomplete/chummer.run-services commit 46551461 tightens the M105 standard verify entrypoint guard so closed-package proof cannot rely on blocked run-helper references.",
    "/docker/chummercomplete/chummer.run-services commit 1b1c5427 pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit 1d5a811f pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit f02e985f tightens the M105 blocked-helper command guard so queue and registry proof cannot cite active-run OODA helper command output.",
    "/docker/chummercomplete/chummer.run-services commit 0f06bcef pins the M105 helper guard proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 1ca535e2 pins the M105 workspace helper proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 25fb4391 pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 41c106c8 pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit b4bdc153 pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit 1c98d6ba pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 83bbc0d4 tightens the M105 workspace duplicate proof guard.",
    "/docker/chummercomplete/chummer.run-services commit 1a0ba130 pins the M105 workspace duplicate proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 63313972 pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 0b038324 tightens M105 local and served release proof uniqueness so duplicate closed-package rows or duplicate package-scoped receipts cannot keep the package green.",
    "/docker/chummercomplete/chummer.run-services commit 447f2a90 pins the M105 workspace uniqueness proof floor so future shards verify the current closed-package guard instead of repeating it.",
    "/docker/chummercomplete/chummer.run-services commit a8f94a63 pins the M105 workspace uniqueness proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 06b0e574 pins the current M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit 79764447 pins the M105 workspace current proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 0f4a31d3 pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit d7788857 tightens the M105 workspace canonical proof floor.",
    "/docker/chummercomplete/chummer.run-services commit f5f414b0 pins the M105 workspace current proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 5e77a853 pins the M105 workspace current proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 23308c16 requires the current M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit 2da59c68 pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit 71e514b2 pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit e0d2bff6 pins the M105 workspace queue-frontier guard proof.",
    "/docker/chummercomplete/chummer.run-services commit c6f628ef pins the M105 verifier to the canonical queue-frontier proof floor.",
    "/docker/chummercomplete/chummer.run-services commit fa17ff4d tightens the M105 workspace queue task guard so completed-package proof must retain the exact assigned successor task text.",
    "/docker/chummercomplete/chummer.run-services commit 72f96452 pins the M105 workspace task guard proof.",
    "/docker/chummercomplete/chummer.run-services commit 664737cb pins the current M105 workspace task guard floor.",
    "/docker/chummercomplete/chummer.run-services commit 138d84ef pins the latest M105 workspace task guard floor.",
    "/docker/chummercomplete/chummer.run-services commit 109face0 pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 28b9e40a pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit f6cd760e tightens the M105 verifier to require the current queue-cited workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 03517936 tightens the M105 restore API proof guard so completed-package proof fails if /api/v1/campaign-spine/me/restore loses the workspace restore projection route.",
    "/docker/chummercomplete/chummer.run-services commit 57da8fb3 preserves workspace restore receipt observation timestamps for unchanged provenance and conflict receipts and pins the behavior in verifier proof.",
    "/docker/chummercomplete/chummer.run-services commit aa7d6b9a pins the M105 current workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 6add6cc6 pins the M105 workspace proof floor.",
    "/docker/chummercomplete/chummer.run-services commit 4487d01a pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit 9171e3f4 tightens M105 release proof receipt uniqueness so duplicate unscoped workspace or entitlement receipt ids cannot hide beside the closed package receipts.",
    "/docker/chummercomplete/chummer.run-services commit a7e826d3 pins the M105 workspace receipt uniqueness proof floor.",
    "/docker/chummercomplete/chummer.run-services commit d882db69 pins the M105 workspace proof floor guard.",
    "/docker/chummercomplete/chummer.run-services commit db4fe453 tightens M105 served proof route mirroring so public proof shelves cannot drift from local route receipts.",
    "/docker/chummercomplete/chummer.run-services commit 57a5b16d tightens M105 proof commit citation resolution so every registry and queue commit proof citation must resolve locally.",
    "/docker/chummercomplete/chummer.run-services commit 02596ecc tightens M105 proof path scope so registry and queue proof paths must stay inside Chummer.Run.Api, scripts, or tests.",
    "/docker/chummercomplete/chummer.run-services commit a08ba77b tightens M105 embedded proof path scope so prose proof bullets cannot cite paths outside Chummer.Run.Api, scripts, or tests.",
    "/docker/chummercomplete/chummer.run-services commit 9f425d04 tightens M105 package-scoped receipt proof so untracked workspace continuity receipt rows cannot hide beside the canonical receipts.",
    "/docker/chummercomplete/chummer.run-services commit 75dba18c pins the current M105 workspace receipt test proof floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit f221ec3f tightens the M105 worker telemetry proof guard so completed-package evidence cannot cite control-plane helper output or worker-run telemetry summaries.",
    "/docker/chummercomplete/chummer.run-services commit 39761fd0 tightens the M105 successor telemetry proof guard so copied remaining-milestone, queue-item, or critical-path summaries cannot close the completed workspace package.",
    "/docker/chummercomplete/chummer.run-services commit d00cf74c tightens the M105 campaign OS proof guard so generated campaign proof cannot cite blocked run-control evidence.",
    "/docker/chummercomplete/chummer.run-services commit 049e2938 pins the M105 campaign proof guard.",
    "/docker/chummercomplete/chummer.run-services commit 58edeea6 tightens the M105 worker-context field guard so queue proof cannot cite task-local run context fields.",
    "/docker/chummercomplete/chummer.run-services commit 586ad535 tightens the M105 successor handoff proof guard so completed-package proof cannot cite copied handoff-context run fields.",
    "/docker/chummercomplete/chummer.run-services commit 54d3756f tightens the M105 successor prompt proof guard so copied successor frontier id, assigned package, and execution-rule fields cannot close the completed workspace package.",
    "/docker/chummercomplete/chummer.run-services commit c6f0439e pins the M105 successor handoff proof floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit db056eb5 pins the M105 successor prompt proof floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 19536ab1 pins the M105 workspace proof floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 3eb87a75 pins the M105 workspace proof floor guard so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 3b854764 tightens the M105 workspace queue scope guard so completed-package proof cannot widen allowed paths or owned surfaces.",
    "/docker/chummercomplete/chummer.run-services commit 44bada17 pins the M105 workspace queue scope proof so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 31b76424 tightens the M105 workspace materializer proof so committed release receipts must be reproducible from scripts/materialize_hub_local_release_proof.py.",
    "/docker/chummercomplete/chummer.run-services commit 121f3571 pins the M105 workspace materializer proof floor so future shards verify the latest closed-package guard.",
    "/docker/chummercomplete/chummer.run-services commit 3d77bb73 tightens the M105 active-run handoff transcript guard so copied prompt, model, and stderr-tail fields cannot close the completed workspace package.",
    "/docker/chummercomplete/chummer.run-services commit bbfe3722 tightens the M105 package receipt metadata guard so wrong-frontier package receipts cannot sit beside the closed workspace continuity receipts.",
    "/docker/chummercomplete/chummer.run-services commit 9d1fe095 tightens the M105 release-proof package mirror guard so top-level and package-list closure metadata cannot drift.",
    "/docker/chummercomplete/chummer.run-services commit 2f85eb13 hardens M105 restore conflict recovery receipts so blocking server-plane conflicts keep an actionable resolution fallback.",
    "/docker/chummercomplete/chummer.run-services/scripts/verify_workspace_restore_receipts.py",
    "/docker/chummercomplete/chummer.run-services/scripts/materialize_hub_local_release_proof.py",
    "/docker/chummercomplete/chummer.run-services/scripts/ai/verify.sh",
    "/docker/chummercomplete/chummer.run-services/tests/test_workspace_restore_commit_resolution.py",
    "/docker/chummercomplete/chummer.run-services/tests/test_workspace_restore_queue_frontier_guard.py",
    "python3 scripts/verify_workspace_restore_receipts.py",
    "python3 -m unittest tests/test_workspace_restore_receipts.py tests/test_workspace_restore_queue_frontier_guard.py tests/test_workspace_restore_commit_resolution.py",
    "dotnet test Chummer.Tests/Chummer.Tests.csproj --filter \"CampaignSpineRestoreReceiptTests|CampaignWorkspaceServerPlaneServiceTests|CampaignOsLocalProofMaterializerTests\" --no-restore",
    "allowed_paths:\n      - Chummer.Run.Api\n      - scripts\n      - tests\n    owned_surfaces:",
    "workspace_restore:provenance",
    "entitlement_sync:conflict_receipts",
]

FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "TASK_LOCAL_TELEMETRY.generated.json",
    "ACTIVE_RUN_HANDOFF",
    "ACTIVE_RUN_HANDOFF.generated.md",
    "task-local telemetry",
    "shard runtime handoff",
    "Shard Runtime Handoff",
    "Recent stderr tail",
    "Prompt path:",
    "Selected account:",
    "Selected model:",
    "Open milestone ids:",
    "successor-wave telemetry",
    "frontier_briefs",
    "successor frontier detail",
    "successor frontier ids",
    "assigned successor queue package",
    "execution rules inside this run",
    "required order",
    "first_commands",
    "polling_disabled",
    "polling disabled",
    "runtime_handoff_path",
    "status_query_supported",
    "status query",
    "successor_queue_path",
    "successor_registry_path",
    "remaining milestones",
    "remaining queue items",
    "critical path",
    "active-run helper",
    "active-run helper command",
    "active-run helper commands",
    "operator telemetry",
    "operator/OODA",
    "operator OODA",
    "supervisor status",
    "supervisor eta",
    "status helper",
    "eta helper",
    "design_supervisor_ooda",
    "ooda_design_supervisor.py",
    "run_ooda_design_supervisor_until_quiet",
    "/var/lib/codex-fleet",
]


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"missing required source file: {path}")
    return path.read_text(encoding="utf-8")


def read_absolute_text(path: Path, label: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"missing required {label}: {path}")
    return path.read_text(encoding="utf-8")


def extract_registry_task_block(text: str) -> str:
    marker = "      - id: 105.1"
    start = text.find(marker)
    if start == -1:
        return ""

    next_task = text.find("\n      - id:", start + len(marker))
    next_milestone = text.find("\n  - id:", start + len(marker))
    candidates = [index for index in [next_task, next_milestone] if index != -1]
    end = min(candidates) if candidates else len(text)
    return text[start:end]


def count_registry_task_blocks(text: str) -> int:
    return text.count("      - id: 105.1\n")


def extract_queue_package_block(text: str) -> str:
    marker = f"    package_id: {PACKAGE_ID}\n"
    package_id_index = text.find(marker)
    if package_id_index == -1:
        return ""

    start = text.rfind("\n  - title:", 0, package_id_index)
    if start == -1:
        start = package_id_index
    else:
        start += 1

    end = text.find("\n  - title:", package_id_index + len(marker))
    if end == -1:
        end = len(text)
    return text[start:end]


def count_queue_package_blocks(text: str) -> int:
    return text.count(f"    package_id: {PACKAGE_ID}\n")


def extract_queue_scalar_list(block: str, section_name: str) -> list[str] | None:
    marker = f"    {section_name}:\n"
    start = block.find(marker)
    if start == -1:
        return None

    values: list[str] = []
    for line in block[start + len(marker):].splitlines():
        if line.startswith("    ") and not line.startswith("      - "):
            break
        if line.startswith("      - "):
            values.append(line.removeprefix("      - ").strip())

    return values


def require_markers(label: str, text: str, markers: list[str], missing: list[str]) -> None:
    for marker in markers:
        if marker not in text:
            missing.append(f"{label}: {marker}")


def flatten_required_markers(payload: dict[str, object]) -> set[str]:
    raw_markers = payload.get("required_markers")
    if not isinstance(raw_markers, dict):
        raise ValueError("proof required_markers must be an object")

    markers: set[str] = set()
    for journey_id, journey_markers in raw_markers.items():
        if not isinstance(journey_id, str) or not isinstance(journey_markers, list):
            raise ValueError("proof required_markers must map journey ids to marker arrays")
        for marker in journey_markers:
            if not isinstance(marker, str):
                raise ValueError(f"proof marker for {journey_id} must be a string")
            markers.add(marker)
    return markers


def check_queue_staging(path: Path, label: str, missing: list[str]) -> None:
    try:
        queue_staging_text = read_absolute_text(path, label)
    except FileNotFoundError as exc:
        missing.append(str(exc))
        return

    queue_block = extract_queue_package_block(queue_staging_text)
    if not queue_block:
        missing.append(f"{path}: missing queue package block for {PACKAGE_ID}")
        return

    package_block_count = count_queue_package_blocks(queue_staging_text)
    if package_block_count != 1:
        missing.append(f"{path}: expected exactly one queue package block for {PACKAGE_ID}; found {package_block_count}")

    require_markers(f"{path}:{PACKAGE_ID}", queue_block, QUEUE_STAGING_MARKERS, missing)
    require_queue_scope(f"{path}:{PACKAGE_ID}", queue_block, missing)
    reject_forbidden_markers(f"{path}:{PACKAGE_ID}", queue_block, FORBIDDEN_PROOF_MARKERS, missing)
    reject_out_of_scope_proof_paths(f"{path}:{PACKAGE_ID}", queue_block, missing)


def require_queue_scope(label: str, queue_block: str, missing: list[str]) -> None:
    allowed_paths = extract_queue_scalar_list(queue_block, "allowed_paths")
    if allowed_paths != QUEUE_ALLOWED_PATHS:
        missing.append(f"{label}: allowed_paths must be exactly {QUEUE_ALLOWED_PATHS!r}")

    owned_surfaces = extract_queue_scalar_list(queue_block, "owned_surfaces")
    if owned_surfaces != QUEUE_OWNED_SURFACES:
        missing.append(f"{label}: owned_surfaces must be exactly {QUEUE_OWNED_SURFACES!r}")


def check_queue_staging_blocks_match(missing: list[str]) -> None:
    try:
        fleet_text = read_absolute_text(QUEUE_STAGING_PATH, "fleet queue staging")
        design_text = read_absolute_text(DESIGN_QUEUE_STAGING_PATH, "design queue staging")
    except FileNotFoundError as exc:
        missing.append(str(exc))
        return

    fleet_block = extract_queue_package_block(fleet_text)
    design_block = extract_queue_package_block(design_text)
    if not fleet_block or not design_block:
        return

    if fleet_block != design_block:
        missing.append(
            f"{QUEUE_STAGING_PATH}:{PACKAGE_ID} must match {DESIGN_QUEUE_STAGING_PATH}:{PACKAGE_ID}"
        )


def reject_forbidden_markers(label: str, text: str, markers: list[str], missing: list[str]) -> None:
    normalized_text = text.casefold()
    for marker in markers:
        if marker.casefold() in normalized_text:
            missing.append(f"{label}: forbidden active-run proof marker: {marker}")


def reject_out_of_scope_proof_paths(label: str, text: str, missing: list[str]) -> None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue

        proof_item = line[2:].strip()
        if not proof_item.startswith(PACKAGE_REPO_ROOT) and PACKAGE_REPO_ROOT not in proof_item:
            continue

        for match in re.finditer(re.escape(PACKAGE_REPO_ROOT) + r"(?P<target>[^\s,;:)]+)", proof_item):
            relative_path = match.group("target").rstrip(".,")
            if relative_path.startswith("commit"):
                continue
            if not relative_path.startswith(ALLOWED_PROOF_PATH_PREFIXES):
                missing.append(
                    f"{label}: proof path must stay inside allowed package roots "
                    f"{', '.join(ALLOWED_PROOF_PATH_PREFIXES)}: {PACKAGE_REPO_ROOT}{relative_path}"
                )


def check_local_release_proof(path: Path, missing: list[str]) -> None:
    if not path.is_file():
        missing.append(f"missing local release proof: {path}")
        return

    proof_text = path.read_text(encoding="utf-8")
    reject_forbidden_markers(str(path), proof_text, FORBIDDEN_PROOF_MARKERS, missing)

    try:
        payload = json.loads(proof_text)
    except json.JSONDecodeError as exc:
        missing.append(f"invalid local release proof: {path}: {exc}")
        return

    if payload.get("status") != "passed":
        missing.append(f"{path}: status must be passed")

    package = payload.get("successor_queue_package")
    if not isinstance(package, dict):
        missing.append(f"{path}: missing successor_queue_package")
    else:
        for key, expected in LOCAL_RELEASE_PROOF_PACKAGE.items():
            if package.get(key) != expected:
                missing.append(f"{path}: successor_queue_package.{key} must be {expected!r}")

    packages = payload.get("successor_queue_packages")
    package_list = [item for item in packages if isinstance(item, dict)] if isinstance(packages, list) else []
    closed_packages = [item for item in package_list if item.get("package_id") == PACKAGE_ID]
    if len(closed_packages) != 1:
        missing.append(
            f"{path}: successor_queue_packages must contain exactly one {PACKAGE_ID}; found {len(closed_packages)}"
        )
    closed_package = closed_packages[0] if closed_packages else None
    if not isinstance(closed_package, dict):
        missing.append(f"{path}: successor_queue_packages missing {PACKAGE_ID}")
    else:
        if isinstance(package, dict) and package != closed_package:
            missing.append(
                f"{path}: successor_queue_package must mirror successor_queue_packages[{PACKAGE_ID}] exactly"
            )
        for key, expected in LOCAL_RELEASE_PROOF_PACKAGE.items():
            if closed_package.get(key) != expected:
                missing.append(f"{path}: successor_queue_packages[{PACKAGE_ID}].{key} must be {expected!r}")

    proof_routes = payload.get("proof_routes")
    proof_route_set = {item for item in proof_routes if isinstance(item, str)} if isinstance(proof_routes, list) else set()
    for route in ["/home/work", "/account/work"]:
        if route not in proof_route_set:
            missing.append(f"{path}: proof_routes missing {route}")

    proof_receipts = payload.get("proof_receipts", [])
    proof_receipt_list = [item for item in proof_receipts if isinstance(item, dict)] if isinstance(proof_receipts, list) else []
    receipts = {
        item.get("receipt_id"): item
        for item in proof_receipt_list
        if isinstance(item.get("receipt_id"), str)
    }
    package_scoped_receipts = [
        item
        for item in proof_receipt_list
        if item.get("package_id") == PACKAGE_ID
        and item.get("milestone_id") == MILESTONE_ID
        and item.get("frontier_id") == FRONTIER_ID
    ]
    package_id_receipts = [
        item
        for item in proof_receipt_list
        if item.get("package_id") == PACKAGE_ID
    ]
    package_receipt_ids = {
        item.get("receipt_id")
        for item in package_scoped_receipts
        if isinstance(item.get("receipt_id"), str)
    }
    expected_receipt_ids = set(LOCAL_RELEASE_PROOF_RECEIPTS)
    if package_receipt_ids != expected_receipt_ids:
        missing.append(
            f"{path}: package-scoped proof_receipts for {PACKAGE_ID} must be {sorted(expected_receipt_ids)!r}"
        )
    if len(package_scoped_receipts) != len(expected_receipt_ids):
        missing.append(
            f"{path}: package-scoped proof_receipts for {PACKAGE_ID} must contain only "
            f"{sorted(expected_receipt_ids)!r}; found {len(package_scoped_receipts)} row(s)"
        )
    if len(package_id_receipts) != len(expected_receipt_ids):
        missing.append(
            f"{path}: proof_receipts with package_id {PACKAGE_ID} must be exactly "
            f"{sorted(expected_receipt_ids)!r} at milestone {MILESTONE_ID} and frontier {FRONTIER_ID}; "
            f"found {len(package_id_receipts)} row(s)"
        )
    for item in package_id_receipts:
        receipt_id = item.get("receipt_id")
        if (
            receipt_id not in expected_receipt_ids
            or item.get("milestone_id") != MILESTONE_ID
            or item.get("frontier_id") != FRONTIER_ID
        ):
            missing.append(
                f"{path}: proof_receipts with package_id {PACKAGE_ID} contains "
                f"non-canonical package metadata for receipt_id {receipt_id!r}"
            )
    for item in package_scoped_receipts:
        receipt_id = item.get("receipt_id")
        if receipt_id not in expected_receipt_ids:
            missing.append(
                f"{path}: package-scoped proof_receipts for {PACKAGE_ID} contains non-canonical receipt_id {receipt_id!r}"
            )
    for expected_receipt_id in expected_receipt_ids:
        global_matching_receipt_count = sum(
            1
            for item in proof_receipt_list
            if isinstance(item, dict)
            and item.get("receipt_id") == expected_receipt_id
        )
        if global_matching_receipt_count != 1:
            missing.append(
                f"{path}: proof_receipts must contain exactly one {expected_receipt_id}; found {global_matching_receipt_count}"
            )

        matching_receipt_count = sum(
            1
            for item in proof_receipt_list
            if isinstance(item, dict)
            and item.get("package_id") == PACKAGE_ID
            and item.get("milestone_id") == MILESTONE_ID
            and item.get("frontier_id") == FRONTIER_ID
            and item.get("receipt_id") == expected_receipt_id
        )
        if matching_receipt_count != 1:
            missing.append(
                f"{path}: proof_receipts must contain exactly one package-scoped {expected_receipt_id}; found {matching_receipt_count}"
            )

    for receipt_id, expected in LOCAL_RELEASE_PROOF_RECEIPTS.items():
        receipt = receipts.get(receipt_id)
        if not isinstance(receipt, dict):
            missing.append(f"{path}: proof_receipts missing {receipt_id}")
            continue

        for key, expected_value in {
            "package_id": PACKAGE_ID,
            "milestone_id": MILESTONE_ID,
            "frontier_id": FRONTIER_ID,
        }.items():
            if receipt.get(key) != expected_value:
                missing.append(f"{path}: {receipt_id}.{key} must be {expected_value!r}")

        for key in ["routes", "surfaces"]:
            values = receipt.get(key)
            if values != expected[key]:
                missing.append(f"{path}: {receipt_id}.{key} must match {expected[key]!r}")

        summary = receipt.get("summary")
        if not isinstance(summary, str):
            missing.append(f"{path}: {receipt_id}.summary must be a string")
        else:
            for marker in expected["summary_markers"]:
                if marker not in summary:
                    missing.append(f"{path}: {receipt_id}.summary missing {marker}")


def read_release_proof_payload(path: Path, label: str, missing: list[str]) -> dict[str, object] | None:
    if not path.is_file():
        missing.append(f"missing {label}: {path}")
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        missing.append(f"invalid {label}: {path}: {exc}")
        return None

    if not isinstance(payload, dict):
        missing.append(f"invalid {label}: {path}: payload must be an object")
        return None

    return payload


def stable_release_payload(payload: dict[str, object]) -> dict[str, object]:
    stable = dict(payload)
    stable.pop("generated_at", None)
    stable.pop("generatedAt", None)
    return stable


def find_closed_package(payload: dict[str, object]) -> dict[str, object] | None:
    packages = payload.get("successor_queue_packages")
    if not isinstance(packages, list):
        return None

    return next(
        (
            item
            for item in packages
            if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID
        ),
        None,
    )


def release_proof_receipt_map(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    receipts = payload.get("proof_receipts")
    if not isinstance(receipts, list):
        return {}

    return {
        item["receipt_id"]: item
        for item in receipts
        if isinstance(item, dict) and isinstance(item.get("receipt_id"), str)
    }


def check_served_release_proof_matches_local(missing: list[str]) -> None:
    local_payload = read_release_proof_payload(
        LOCAL_RELEASE_PROOF_PATH,
        "local release proof",
        missing,
    )
    served_payload = read_release_proof_payload(
        SERVED_RELEASE_PROOF_PATH,
        "served release proof",
        missing,
    )
    if local_payload is None or served_payload is None:
        return

    if local_payload.get("successor_queue_package") != served_payload.get("successor_queue_package"):
        missing.append(
            f"{SERVED_RELEASE_PROOF_PATH}: successor_queue_package must match {LOCAL_RELEASE_PROOF_PATH}"
        )

    if local_payload.get("proof_routes") != served_payload.get("proof_routes"):
        missing.append(
            f"{SERVED_RELEASE_PROOF_PATH}: proof_routes must match {LOCAL_RELEASE_PROOF_PATH}"
        )

    local_package = find_closed_package(local_payload)
    served_package = find_closed_package(served_payload)
    if local_package != served_package:
        missing.append(
            f"{SERVED_RELEASE_PROOF_PATH}: successor_queue_packages[{PACKAGE_ID}] must match {LOCAL_RELEASE_PROOF_PATH}"
        )

    local_receipts = release_proof_receipt_map(local_payload)
    served_receipts = release_proof_receipt_map(served_payload)
    for receipt_id in LOCAL_RELEASE_PROOF_RECEIPTS:
        if local_receipts.get(receipt_id) != served_receipts.get(receipt_id):
            missing.append(
                f"{SERVED_RELEASE_PROOF_PATH}: proof_receipts[{receipt_id}] must match {LOCAL_RELEASE_PROOF_PATH}"
            )


def check_materializer_matches_local_release_proof(missing: list[str]) -> None:
    local_payload = read_release_proof_payload(
        LOCAL_RELEASE_PROOF_PATH,
        "local release proof",
        missing,
    )
    if local_payload is None:
        return

    if not MATERIALIZER_PATH.is_file():
        missing.append(f"missing local release proof materializer: {MATERIALIZER_PATH}")
        return

    with tempfile.TemporaryDirectory(prefix="workspace-restore-materializer-") as temp_dir:
        output_path = Path(temp_dir) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
        result = subprocess.run(
            [
                sys.executable,
                str(MATERIALIZER_PATH),
                str(output_path),
                str(local_payload.get("base_url") or ""),
                str(local_payload.get("compose_file") or ""),
                str(local_payload.get("playwright_timeout_seconds") or 0),
                "true" if local_payload.get("edge_rebuild_skipped") is True else "false",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            missing.append(
                f"{MATERIALIZER_PATH}: failed to materialize local release proof: {result.stderr or result.stdout}"
            )
            return

        generated_payload = read_release_proof_payload(
            output_path,
            "materialized local release proof",
            missing,
        )
        if generated_payload is None:
            return

    if stable_release_payload(generated_payload) != stable_release_payload(local_payload):
        missing.append(
            f"{MATERIALIZER_PATH}: materialized proof must match {LOCAL_RELEASE_PROOF_PATH} aside from timestamps"
        )


def check_required_local_commits(missing: list[str]) -> None:
    for commit in REQUIRED_LOCAL_COMMITS:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if result.returncode != 0:
            missing.append(f"{ROOT}: required local commit does not resolve: {commit}")


def check_standard_verify_entrypoint(missing: list[str]) -> None:
    relative_path = "scripts/ai/verify.sh"
    try:
        verify_text = read_text(relative_path)
    except FileNotFoundError as exc:
        missing.append(str(exc))
        return

    require_markers(relative_path, verify_text, STANDARD_VERIFY_MARKERS, missing)
    reject_forbidden_markers(relative_path, verify_text, FORBIDDEN_PROOF_MARKERS, missing)


def main() -> int:
    missing: list[str] = []

    for relative_path, markers in SOURCE_MARKERS.items():
        try:
            text = read_text(relative_path)
        except FileNotFoundError as exc:
            missing.append(str(exc))
            continue

        for marker in markers:
            if marker not in text:
                missing.append(f"{relative_path}: {marker}")

    if not PROOF_PATH.is_file():
        missing.append(f"missing local campaign OS proof: {PROOF_PATH}")
    else:
        try:
            proof_text = PROOF_PATH.read_text(encoding="utf-8")
            reject_forbidden_markers(str(PROOF_PATH), proof_text, FORBIDDEN_PROOF_MARKERS, missing)
            payload = json.loads(proof_text)
            proof_markers = flatten_required_markers(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            missing.append(f"invalid local campaign OS proof: {PROOF_PATH}: {exc}")
        else:
            for marker in PROOF_MARKERS:
                if marker not in proof_markers:
                    missing.append(f"{PROOF_PATH}: {marker}")

    try:
        registry_text = read_absolute_text(REGISTRY_PATH, "successor registry")
    except FileNotFoundError as exc:
        missing.append(str(exc))
    else:
        task_block_count = count_registry_task_blocks(registry_text)
        if task_block_count != 1:
            missing.append(f"{REGISTRY_PATH}: expected exactly one registry task block for 105.1; found {task_block_count}")

        registry_block = extract_registry_task_block(registry_text)
        if not registry_block:
            missing.append(f"{REGISTRY_PATH}: missing registry task block for 105.1")
        else:
            require_markers(f"{REGISTRY_PATH}:105.1", registry_block, REGISTRY_MARKERS, missing)
            reject_forbidden_markers(
                f"{REGISTRY_PATH}:105.1",
                registry_block,
                FORBIDDEN_PROOF_MARKERS,
                missing,
            )
            reject_out_of_scope_proof_paths(f"{REGISTRY_PATH}:105.1", registry_block, missing)

    check_queue_staging(QUEUE_STAGING_PATH, "fleet queue staging", missing)
    check_queue_staging(DESIGN_QUEUE_STAGING_PATH, "design queue staging", missing)
    check_queue_staging_blocks_match(missing)
    check_local_release_proof(LOCAL_RELEASE_PROOF_PATH, missing)
    check_local_release_proof(SERVED_RELEASE_PROOF_PATH, missing)
    check_served_release_proof_matches_local(missing)
    check_materializer_matches_local_release_proof(missing)
    check_required_local_commits(missing)
    check_standard_verify_entrypoint(missing)

    if missing:
        for item in missing:
            print(f"workspace_restore_receipts_missing: {item}", file=sys.stderr)
        return 1

    print("workspace restore receipt proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
