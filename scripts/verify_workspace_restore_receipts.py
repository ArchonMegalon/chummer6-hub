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
    "allowed_paths": [
        "Chummer.Run.Api",
        "scripts",
        "tests",
    ],
    "owned_surfaces": [
        "workspace_restore:provenance",
        "entitlement_sync:conflict_receipts",
    ],
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
    "operator telemetry",
    "design_supervisor_ooda",
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


def reject_forbidden_markers(label: str, text: str, markers: list[str], missing: list[str]) -> None:
    for marker in markers:
        if marker in text:
            missing.append(f"{label}: forbidden active-run proof marker: {marker}")


def check_local_release_proof(path: Path, missing: list[str]) -> None:
    if not path.is_file():
        missing.append(f"missing local release proof: {path}")
        return

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
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
            value_set = {item for item in values if isinstance(item, str)} if isinstance(values, list) else set()
            for required in expected[key]:
                if required not in value_set:
                    missing.append(f"{path}: {receipt_id}.{key} missing {required}")

        summary = receipt.get("summary")
        if not isinstance(summary, str):
            missing.append(f"{path}: {receipt_id}.summary must be a string")
        else:
            for marker in expected["summary_markers"]:
                if marker not in summary:
                    missing.append(f"{path}: {receipt_id}.summary missing {marker}")


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
    check_local_release_proof(LOCAL_RELEASE_PROOF_PATH, missing)
    check_local_release_proof(SERVED_RELEASE_PROOF_PATH, missing)
    check_required_local_commits(missing)

    if missing:
        for item in missing:
            print(f"workspace_restore_receipts_missing: {item}", file=sys.stderr)
        return 1

    print("workspace restore receipt proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
