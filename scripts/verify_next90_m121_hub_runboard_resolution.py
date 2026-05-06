#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m121-hub-persist-session-turn-ledger-handoff-runboard-state-and-r"
WORK_TASK_ID = "121.5"
TITLE = "Persist session turn-ledger handoff, runboard state, and ResolutionReport draft continuity without owning engine math."
TASK = "Persist session turn-ledger handoff, runboard state, and ResolutionReport draft continuity without owning engine math."
FRONTIER_ID = 7165194744
MILESTONE_ID = 121
WAVE = "W15"
STATUS = "not_started"
REPO = "chummer6-hub"
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["persist_session_turn_ledger_handoff:hub"]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "task-local telemetry",
    "shard runtime handoff",
    "supervisor status",
    "supervisor eta",
    "operator telemetry",
]
PACKAGE_PROOF = {
    "package_id": PACKAGE_ID,
    "work_task_id": WORK_TASK_ID,
    "title": TITLE,
    "task": TASK,
    "frontier_id": FRONTIER_ID,
    "milestone_id": MILESTONE_ID,
    "wave": WAVE,
    "repo": REPO,
    "status": STATUS,
    "allowed_paths": ALLOWED_PATHS,
    "owned_surfaces": OWNED_SURFACES,
}

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs": [
        '"runboard_state" => "runboard_state",',
        '"resolution_report_draft" => "resolution_report_draft",',
        '"runboard_state" => $"{runTitle} runboard state",',
        '"resolution_report_draft" => $"{runTitle} ResolutionReport draft",',
        '"runboard_state" => $"Generated a runboard state packet for {subject} so active-scene return, open objectives, and the GM-facing turn-ledger handoff stay reviewable on the same governed lane.",',
        '"resolution_report_draft" => $"Generated a ResolutionReport draft for {subject} so runboard state, contested-turn follow-through, and next-session continuity stay reviewable without the hub owning engine math.",',
        'string turnLedgerHandoff = activeScene is null',
        '? $"Turn ledger handoff: no active scene is pinned yet, but {openObjectiveCount} open objective(s) and {consequenceCount} consequence signal(s) remain on the shared return lane."',
        ': $"Turn ledger handoff: {activeScene.Title} stays pinned at {activeScene.Revision} with {openObjectiveCount} open objective(s) and {consequenceCount} consequence signal(s) carried forward.";',
        'packageKind == "runboard_state"',
        '? $"Runboard state: {workspace.ActiveSceneSummary ?? workspace.ReturnSummary}"',
        'packageKind == "resolution_report_draft"',
        '? "ResolutionReport draft posture: contested-turn follow-through stays draft-scoped on the shared continuity lane until an approved report supersedes it."',
    ],
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs": [
        '"runboard_state" => "runboard state",',
        '"resolution_report_draft" => "ResolutionReport draft",',
        'AftermathRecapPackageProjection? aftermathPackage = orderedAftermathPackages',
        'Kind: DescribeAftermathChangePacketKind(package.PackageKind),',
        '"runboard_state" => "Runboard state",',
        '"resolution_report_draft" => "ResolutionReport draft",',
        '"runboard_state" => "runboard_state",',
        '"resolution_report_draft" => "resolution_report",',
    ],
    "Chummer.Run.Api/Views/Accounts/Account.cshtml": [
        '<option value="runboard_state">Runboard state</option>',
        '<option value="resolution_report_draft">ResolutionReport draft</option>',
        'case "runboard_state":',
        'case "resolution_report_draft":',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        'PackageKind: "runboard_state",',
        'Assert(runboardStatePayload.EvidenceLines.Any(item => item.Contains("Turn ledger handoff:", StringComparison.OrdinalIgnoreCase)), "campaign spine runboard state api should persist turn-ledger handoff evidence lines.");',
        'Assert(runboardStatePayload.EvidenceLines.Any(item => item.Contains("Runboard state:", StringComparison.OrdinalIgnoreCase)), "campaign spine runboard state api should persist runboard-state evidence lines.");',
        'PackageKind: "resolution_report_draft",',
        'Assert(resolutionReportDraftPayload.EvidenceLines.Any(item => item.Contains("Turn ledger handoff:", StringComparison.OrdinalIgnoreCase)), "campaign spine ResolutionReport draft api should persist turn-ledger handoff evidence lines.");',
        'Assert(resolutionReportDraftPayload.EvidenceLines.Any(item => item.Contains("ResolutionReport draft posture:", StringComparison.OrdinalIgnoreCase)), "campaign spine ResolutionReport draft api should persist draft-posture evidence lines.");',
        'Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "runboard_state", StringComparison.Ordinal)) == true, "campaign spine server plane api should name runboard packets explicitly on the bounded what-changed rail.");',
        'Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "resolution_report", StringComparison.Ordinal)) == true, "campaign spine server plane api should name ResolutionReport drafts explicitly on the bounded what-changed rail.");',
    ],
    "tests/RunServicesVerification/CampaignSpineRestoreVerification.cs": [
        '"resolution_report_draft",',
        '"Turn ledger handoff: active scene and open objectives stay attached to the same governed return lane."',
        'VerificationAssert.True(reloadedResolutionDraft.EvidenceLines.Any(item => item.Contains("Turn ledger handoff:", StringComparison.OrdinalIgnoreCase)), "Reloaded ResolutionReport draft packages should preserve turn-ledger handoff evidence.");',
    ],
    "scripts/materialize_next90_m121_hub_runboard_resolution_proof.py": [
        f'"package_id": "{PACKAGE_ID}"',
        f'"frontier_id": {FRONTIER_ID}',
        f'"milestone_id": {MILESTONE_ID}',
        '"persist_session_turn_ledger_handoff:hub": [',
        '"resolution_report_draft_continuity": [',
        '"contract_name": "chummer6-hub.next90_m121_hub_runboard_resolution"',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/materialize_next90_m121_hub_runboard_resolution_proof.py",
        "python3 scripts/verify_next90_m121_hub_runboard_resolution.py",
        "python3 -m unittest tests/test_next90_m121_hub_runboard_resolution_proof.py",
    ],
}

PROOF_MARKERS = [
    'PackageKind: "runboard_state",',
    'Assert(runboardStatePayload.EvidenceLines.Any(item => item.Contains("Turn ledger handoff:", StringComparison.OrdinalIgnoreCase)), "campaign spine runboard state api should persist turn-ledger handoff evidence lines.");',
    'Assert(runboardStatePayload.EvidenceLines.Any(item => item.Contains("Runboard state:", StringComparison.OrdinalIgnoreCase)), "campaign spine runboard state api should persist runboard-state evidence lines.");',
    'Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "runboard_state", StringComparison.Ordinal)) == true, "campaign spine server plane api should name runboard packets explicitly on the bounded what-changed rail.");',
    'PackageKind: "resolution_report_draft",',
    'Assert(resolutionReportDraftPayload.EvidenceLines.Any(item => item.Contains("Turn ledger handoff:", StringComparison.OrdinalIgnoreCase)), "campaign spine ResolutionReport draft api should persist turn-ledger handoff evidence lines.");',
    'Assert(resolutionReportDraftPayload.EvidenceLines.Any(item => item.Contains("ResolutionReport draft posture:", StringComparison.OrdinalIgnoreCase)), "campaign spine ResolutionReport draft api should persist draft-posture evidence lines.");',
    'Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "resolution_report", StringComparison.Ordinal)) == true, "campaign spine server plane api should name ResolutionReport drafts explicitly on the bounded what-changed rail.");',
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M121_HUB_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M121_HUB_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M121_HUB_DESIGN_QUEUE_STAGING",
        str(ROOT / ".codex-design" / "product" / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"),
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M121_HUB_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M121_HUB_PROOF",
        ROOT / ".codex-studio" / "published" / "NEXT90_M121_HUB_RUNBOARD_RESOLUTION.generated.json",
    )
)


def load_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def reject_forbidden_markers(text: str, source: str, errors: list[str]) -> None:
    lowered = text.casefold()
    for marker in FORBIDDEN_PROOF_MARKERS:
        if marker.casefold() in lowered:
            errors.append(f"{source} contains forbidden active-run proof marker: {marker}")


def verify_source_markers(errors: list[str]) -> None:
    for relative_path, markers in SOURCE_MARKERS.items():
        text = read_text(relative_path)
        reject_forbidden_markers(text, relative_path, errors)
        for marker in markers:
            if marker not in text:
                errors.append(f"{relative_path} missing marker: {marker}")


def verify_queue_authority(errors: list[str], path: Path) -> None:
    if not path.is_file():
        errors.append(f"missing queue staging file: {path}")
        return

    payload = load_yaml(path) or {}
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        errors.append(f"{path}: items is missing")
        return

    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        errors.append(f"{path}: expected exactly one {PACKAGE_ID} row, found {len(matches)}")
        return

    item = matches[0]
    expected_fields = {
        "title": TITLE,
        "task": TASK,
        "work_task_id": WORK_TASK_ID,
        "frontier_id": FRONTIER_ID,
        "milestone_id": MILESTONE_ID,
        "status": STATUS,
        "wave": WAVE,
        "repo": REPO,
    }
    for key, value in expected_fields.items():
        if item.get(key) != value:
            errors.append(f"{path}: {PACKAGE_ID} {key} must be {value!r}")

    if item.get("allowed_paths") != ALLOWED_PATHS:
        errors.append(f"{path}: allowed_paths must be {ALLOWED_PATHS!r}")
    if item.get("owned_surfaces") != OWNED_SURFACES:
        errors.append(f"{path}: owned_surfaces must be {OWNED_SURFACES!r}")


def verify_successor_registry(errors: list[str], path: Path) -> None:
    if not path.is_file():
        errors.append(f"missing successor registry file: {path}")
        return

    payload = load_yaml(path) or {}
    milestones = payload.get("milestones") if isinstance(payload, dict) else None
    if not isinstance(milestones, list):
        errors.append(f"{path}: milestones is missing")
        return

    milestone = next((item for item in milestones if isinstance(item, dict) and item.get("id") == MILESTONE_ID), None)
    if milestone is None:
        errors.append(f"{path}: milestone {MILESTONE_ID} is missing")
        return

    if milestone.get("title") != "Live action economy, source anchors, and GM Runboard":
        errors.append(f"{path}: milestone {MILESTONE_ID} title drifted")

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        errors.append(f"{path}: milestone {MILESTONE_ID} work_tasks is missing")
        return

    task = next((item for item in work_tasks if isinstance(item, dict) and str(item.get("id")) == WORK_TASK_ID), None)
    if task is None:
        errors.append(f"{path}: work task {WORK_TASK_ID} is missing")
        return

    if task.get("owner") != REPO:
        errors.append(f"{path}: work task {WORK_TASK_ID} owner drifted")
    if task.get("title") != TITLE:
        errors.append(f"{path}: work task {WORK_TASK_ID} title drifted")


def verify_proof(errors: list[str], path: Path) -> None:
    if not path.is_file():
        errors.append(f"missing generated proof: {path}")
        return

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract_name") != "chummer6-hub.next90_m121_hub_runboard_resolution":
        errors.append(f"{path}: contract_name drifted")
    if payload.get("package_proof") != PACKAGE_PROOF:
        errors.append(f"{path}: package_proof drifted")
    if payload.get("source_file") != "tests/RunServicesSmoke/Program.cs":
        errors.append(f"{path}: source_file must be tests/RunServicesSmoke/Program.cs")

    required_markers = payload.get("required_markers")
    if not isinstance(required_markers, dict):
        errors.append(f"{path}: required_markers is missing")
        return

    proof_markers: list[str] = []
    for section_name in ("persist_session_turn_ledger_handoff:hub", "resolution_report_draft_continuity"):
        section_markers = required_markers.get(section_name)
        if not isinstance(section_markers, list):
            errors.append(f"{path}: {section_name} markers are missing")
            continue
        proof_markers.extend(section_markers)

    for marker in PROOF_MARKERS:
        if marker not in proof_markers:
            errors.append(f"{path}: missing proof marker {marker!r}")

    encoded_blob = json.dumps(payload, sort_keys=True)
    reject_forbidden_markers(encoded_blob, str(path), errors)


def main() -> int:
    errors: list[str] = []
    verify_source_markers(errors)
    verify_queue_authority(errors, FLEET_QUEUE_STAGING_PATH)
    verify_queue_authority(errors, DESIGN_QUEUE_STAGING_PATH)
    verify_successor_registry(errors, SUCCESSOR_REGISTRY_PATH)
    verify_proof(errors, PROOF_PATH)

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("next90 m121 hub runboard resolution proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
