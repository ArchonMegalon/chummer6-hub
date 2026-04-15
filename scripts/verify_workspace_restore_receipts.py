#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
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
PACKAGE_ID = "next90-m105-hub-workspace-continuity"
LANDED_COMMIT = "4d4b3856"
FRONTIER_ID = 4623636482
MILESTONE_ID = 105
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
    "717af57e",
    "346c3ede",
    "8d59d95f",
    "1b8d9363",
    "e0521ca5",
    "06e2ec99",
    "cb560573",
    "7c92635e",
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
    "af336c17",
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
    "Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs": [
        "RestoreProvenanceReceipts: ProjectRestoreProvenanceReceipts(context.Restore.ProvenanceReceipts)",
        "RestoreConflictReceipts: ProjectRestoreConflictReceipts(context.Restore.ConflictReceipts)",
        "ResolveRestoreReceiptSurface(receipt.Surface, receipt.Kind)",
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
    "/docker/chummercomplete/chummer.run-services commit 46551461 tightens the M105 standard verify entrypoint guard so closed-package proof cannot rely on blocked run-helper references.",
    "/docker/chummercomplete/chummer.run-services/scripts/verify_workspace_restore_receipts.py fail-closes missing source/proof markers",
    "python3 scripts/verify_workspace_restore_receipts.py exits 0.",
    "python3 -m unittest tests/test_workspace_restore_receipts.py exits 0.",
    "python3 -m unittest tests/test_workspace_restore_receipts.py tests/test_workspace_restore_queue_frontier_guard.py tests/test_workspace_restore_commit_resolution.py exits 0.",
    "dotnet test Chummer.Tests/Chummer.Tests.csproj --filter \"CampaignSpineRestoreReceiptTests|CampaignWorkspaceServerPlaneServiceTests|CampaignOsLocalProofMaterializerTests\" --no-restore exits 0",
]

QUEUE_STAGING_MARKERS = [
    "title: Emit provenance and conflict receipts for workspace restore and continuity",
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
    "/docker/chummercomplete/chummer.run-services commit 46551461 tightens the M105 standard verify entrypoint guard so closed-package proof cannot rely on blocked run-helper references.",
    "/docker/chummercomplete/chummer.run-services/scripts/verify_workspace_restore_receipts.py",
    "/docker/chummercomplete/chummer.run-services/scripts/materialize_hub_local_release_proof.py",
    "/docker/chummercomplete/chummer.run-services/scripts/ai/verify.sh",
    "/docker/chummercomplete/chummer.run-services/tests/test_workspace_restore_commit_resolution.py",
    "python3 scripts/verify_workspace_restore_receipts.py",
    "python3 -m unittest tests/test_workspace_restore_receipts.py tests/test_workspace_restore_queue_frontier_guard.py tests/test_workspace_restore_commit_resolution.py",
    "dotnet test Chummer.Tests/Chummer.Tests.csproj --filter \"CampaignSpineRestoreReceiptTests|CampaignWorkspaceServerPlaneServiceTests|CampaignOsLocalProofMaterializerTests\" --no-restore",
    "allowed_paths:\n      - Chummer.Run.Api\n      - scripts\n      - tests\n    owned_surfaces:",
    "workspace_restore:provenance",
    "entitlement_sync:conflict_receipts",
]

FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "active-run helper",
    "active-run helper command",
    "operator telemetry",
    "operator/OODA",
    "design_supervisor_ooda",
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

    require_markers(f"{path}:{PACKAGE_ID}", queue_block, QUEUE_STAGING_MARKERS, missing)
    reject_forbidden_markers(f"{path}:{PACKAGE_ID}", queue_block, FORBIDDEN_PROOF_MARKERS, missing)


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
    closed_package = next((item for item in package_list if item.get("package_id") == PACKAGE_ID), None)
    if not isinstance(closed_package, dict):
        missing.append(f"{path}: successor_queue_packages missing {PACKAGE_ID}")
    else:
        for key, expected in LOCAL_RELEASE_PROOF_PACKAGE.items():
            if closed_package.get(key) != expected:
                missing.append(f"{path}: successor_queue_packages[{PACKAGE_ID}].{key} must be {expected!r}")

    proof_routes = payload.get("proof_routes")
    proof_route_set = {item for item in proof_routes if isinstance(item, str)} if isinstance(proof_routes, list) else set()
    for route in ["/home/work", "/account/work"]:
        if route not in proof_route_set:
            missing.append(f"{path}: proof_routes missing {route}")

    receipts = {
        item.get("receipt_id"): item
        for item in payload.get("proof_receipts", [])
        if isinstance(item, dict)
    }
    package_receipt_ids = {
        receipt_id
        for receipt_id, receipt in receipts.items()
        if isinstance(receipt_id, str)
        and receipt.get("package_id") == PACKAGE_ID
        and receipt.get("milestone_id") == MILESTONE_ID
        and receipt.get("frontier_id") == FRONTIER_ID
    }
    expected_receipt_ids = set(LOCAL_RELEASE_PROOF_RECEIPTS)
    if package_receipt_ids != expected_receipt_ids:
        missing.append(
            f"{path}: package-scoped proof_receipts for {PACKAGE_ID} must be {sorted(expected_receipt_ids)!r}"
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
            payload = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
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

    check_queue_staging(QUEUE_STAGING_PATH, "fleet queue staging", missing)
    check_queue_staging(DESIGN_QUEUE_STAGING_PATH, "design queue staging", missing)
    check_queue_staging_blocks_match(missing)
    check_local_release_proof(LOCAL_RELEASE_PROOF_PATH, missing)
    check_local_release_proof(SERVED_RELEASE_PROOF_PATH, missing)
    check_served_release_proof_matches_local(missing)
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
