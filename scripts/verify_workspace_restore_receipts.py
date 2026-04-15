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


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"missing required source file: {path}")
    return path.read_text(encoding="utf-8")


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

    if missing:
        for item in missing:
            print(f"workspace_restore_receipts_missing: {item}", file=sys.stderr)
        return 1

    print("workspace restore receipt proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
