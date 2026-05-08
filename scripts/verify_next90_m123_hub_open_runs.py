#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m123-hub-build-openrun-listing-join-request-roster-schedule-meeti"
WORK_TASK_ID = "123.1"
TITLE = "Build OpenRun listing, join request, roster, schedule, meeting-handoff, and closeout orchestration."
TASK = "Build OpenRun listing, join request, roster, schedule, meeting-handoff, and closeout orchestration."
FRONTIER_ID = 8531582567
MILESTONE_ID = 123
WAVE = "W16"
STATUS = "not_started"
REPO = "chummer6-hub"
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["build_openrun_listing_join_request:hub"]
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
    "Chummer.Run.Api/Contracts/OpenRunContracts.cs": [
        "public sealed record OpenRunListingProjection(",
        "public sealed record OpenRunStateProjection(",
        "public sealed record OpenRunJoinRequestRequest(",
        "public sealed record OpenRunRosterDecisionRequest(",
        "public sealed record OpenRunScheduleRequest(",
        "public sealed record OpenRunMeetingHandoffRequest(",
        "public sealed record OpenRunCloseoutRequest(",
    ],
    "Chummer.Run.Api/Services/Community/CommunityStore.cs": [
        "public List<OpenRunStateProjection> OpenRuns { get; } = new();",
        "OpenRuns: OpenRuns.OrderByDescending(static item => item.UpdatedAtUtc).ToArray(),",
        "OpenRuns.Clear();",
        "OpenRuns.AddRange(snapshot.OpenRuns ?? Array.Empty<OpenRunStateProjection>());",
    ],
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs": [
        '[HttpGet("me/open-runs")]',
        '[HttpGet("me/workspaces/{workspaceId}/open-runs")]',
        '[HttpPost("me/open-runs/join-requests")]',
        '[HttpPost("me/open-runs/roster-decisions")]',
        '[HttpPost("me/open-runs/schedule")]',
        '[HttpPost("me/open-runs/meeting-handoff")]',
        '[HttpPost("me/open-runs/closeout")]',
        "GetMyOpenRuns(CancellationToken cancellationToken)",
        "RequestMyOpenRunSeat(",
        "ReviewMyOpenRunJoinRequest(",
        "ScheduleMyOpenRun(",
        "PublishMyOpenRunMeetingHandoff(",
        "CloseOutMyOpenRun(",
    ],
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs": [
        "public IReadOnlyList<OpenRunListingProjection> GetOpenRuns(HubUserDto user, InstallLinkingSummaryDto? installLinking = null)",
        "public OpenRunListingProjection RequestOpenRunSeat(",
        "public OpenRunListingProjection ReviewOpenRunJoinRequest(",
        "public OpenRunListingProjection ScheduleOpenRun(",
        "public OpenRunListingProjection PublishOpenRunMeetingHandoff(",
        "public OpenRunListingProjection CloseOutOpenRun(",
        'Kind: "open_run",',
        'Label: "OpenRun coordination",',
        'OpenRun listing opened for {run.Title} on {workspace.CampaignName}.',
        "private static string BuildOpenRunJoinPolicySummary(CampaignWorkspaceProjection workspace, CampaignProjection campaign)",
        "organizer review remains required before roster confirmation.",
    ],
    "tests/RunServicesSmoke/Program.cs": [
        "var openRunsResult = await campaignSpineController.GetMyOpenRuns(CancellationToken.None);",
        "campaign spine api should expose at least one governed open-run listing.",
        "campaign spine open-run join-request api should move the listing onto the join-request rail.",
        "campaign spine open-run roster-decision api should move the listing onto the rostered rail.",
        "campaign spine open-run schedule api should move the listing onto the scheduled rail.",
        "campaign spine open-run meeting-handoff api should move the listing onto the handoff-ready rail.",
        "campaign spine open-run closeout api should move the listing onto the closed-out rail.",
        'string.Equals(item.Kind, "open_run", StringComparison.Ordinal)',
    ],
    "tests/RunServicesVerification/CampaignSpineRestoreVerification.cs": [
        "VerifyOpenRunOrchestrationSurvivesCommunityStoreReload();",
        "private static void VerifyOpenRunOrchestrationSurvivesCommunityStoreReload()",
        "Reloaded open-run listing should preserve the closed-out status.",
        "Reloaded workspace should preserve the open-run coordination change packet.",
    ],
    "scripts/materialize_next90_m123_hub_open_runs_proof.py": [
        f'"package_id": "{PACKAGE_ID}"',
        f'"frontier_id": {FRONTIER_ID}',
        '"build_openrun_listing_join_request:hub": [',
        '"meeting_handoff_closeout:hub": [',
        '"contract_name": "chummer6-hub.next90_m123_hub_open_runs"',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/materialize_next90_m123_hub_open_runs_proof.py",
        "python3 scripts/verify_next90_m123_hub_open_runs.py",
        "python3 -m unittest tests/test_next90_m123_hub_open_runs_proof.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M123_HUB_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M123_HUB_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M123_HUB_DESIGN_QUEUE_STAGING",
        str(ROOT / ".codex-design" / "product" / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"),
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M123_HUB_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M123_HUB_PROOF",
        ROOT / ".codex-studio" / "published" / "NEXT90_M123_HUB_OPEN_RUNS.generated.json",
    )
)


def load_yaml(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return load_target_queue_yaml(text, path)


def load_target_queue_yaml(text: str, path: Path) -> object:
    marker = f"package_id: {PACKAGE_ID}"
    package_index = text.find(marker)
    if package_index < 0:
        raise SystemExit(f"unable to parse yaml file: {path}")

    start_candidates = [
        text.rfind("\n- title:", 0, package_index),
        text.rfind("\n  - title:", 0, package_index),
    ]
    block_start = max(start_candidates)
    if block_start < 0:
        if text.startswith("- title:") or text.startswith("  - title:"):
            block_start = 0
        else:
            raise SystemExit(f"unable to isolate queue block in {path}")
    else:
        block_start += 1

    end_candidates = [index for index in (text.find("\n- title:", package_index), text.find("\n  - title:", package_index)) if index >= 0]
    block_end = min(end_candidates) if end_candidates else len(text)
    block = text[block_start:block_end].rstrip() + "\n"
    payload = yaml.safe_load(block)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise SystemExit(f"unable to normalize queue staging yaml: {path}")

    return {"items": payload}


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
        if path == DESIGN_QUEUE_STAGING_PATH:
            return
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
    if milestone.get("title") != "Open Runs and Community Hub table-formation loop":
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
    if payload.get("contract_name") != "chummer6-hub.next90_m123_hub_open_runs":
        errors.append(f"{path}: contract_name drifted")
    if payload.get("package_proof") != PACKAGE_PROOF:
        errors.append(f"{path}: package_proof drifted")
    if payload.get("source_file") != "tests/RunServicesSmoke/Program.cs":
        errors.append(f"{path}: source_file must be tests/RunServicesSmoke/Program.cs")

    reject_forbidden_markers(json.dumps(payload), str(path), errors)


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

    print("next90 m123 hub open-runs proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
