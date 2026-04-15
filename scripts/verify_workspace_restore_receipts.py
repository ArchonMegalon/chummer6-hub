#!/usr/bin/env python3
from __future__ import annotations

import json
import os
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

REGISTRY_MARKERS = [
    "id: 105.1",
    "owner: chummer6-hub",
    "title: Emit provenance and conflict receipts for roaming workspace and entitlement replication.",
    "status: complete",
    f"landed_commit: {LANDED_COMMIT}",
    f"/docker/chummercomplete/chummer.run-services commit {LANDED_COMMIT} emits workspace_restore provenance receipts",
    "/docker/chummercomplete/chummer.run-services/scripts/verify_workspace_restore_receipts.py fail-closes missing source/proof markers",
    "python3 scripts/verify_workspace_restore_receipts.py exits 0.",
    "python3 -m unittest tests/test_workspace_restore_receipts.py exits 0.",
]

QUEUE_STAGING_MARKERS = [
    "title: Emit provenance and conflict receipts for workspace restore and continuity",
    f"package_id: {PACKAGE_ID}\n",
    "milestone_id: 105",
    "repo: chummer6-hub",
    "status: complete",
    f"landed_commit: {LANDED_COMMIT}",
    "/docker/chummercomplete/chummer.run-services/scripts/verify_workspace_restore_receipts.py",
    "python3 scripts/verify_workspace_restore_receipts.py",
    "python3 -m unittest tests/test_workspace_restore_receipts.py",
    "workspace_restore:provenance",
    "entitlement_sync:conflict_receipts",
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

    check_queue_staging(QUEUE_STAGING_PATH, "fleet queue staging", missing)
    check_queue_staging(DESIGN_QUEUE_STAGING_PATH, "design queue staging", missing)

    if missing:
        for item in missing:
            print(f"workspace_restore_receipts_missing: {item}", file=sys.stderr)
        return 1

    print("workspace restore receipt proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
