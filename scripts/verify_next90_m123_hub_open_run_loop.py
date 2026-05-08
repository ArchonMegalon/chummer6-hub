#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m123-hub-build-openrun-listing-join-request-roster-schedule-meeti"
WORK_TASK_ID = "123.1"
FRONTIER_ID = 8531582567
MILESTONE_ID = 123
PACKAGE_TITLE = "Build OpenRun listing, join request, roster, schedule, meeting-handoff, and closeout orchestration."
PACKAGE_TASK = PACKAGE_TITLE
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W16"
PACKAGE_STATUS = "not_started"
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["build_openrun_listing_join_request:hub"]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "supervisor status",
    "task-local telemetry",
]

SOURCE_MARKERS = {
    "Chummer.Run.Api/Contracts/OpenRunContracts.cs": [
        "public sealed record OpenRunListingProjection(",
        "public sealed record OpenRunJoinRequestProjection(",
        "public sealed record OpenRunCloseoutProjection(",
        "public sealed record OpenRunOrchestrationProjection(",
    ],
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs": [
        '[HttpGet("me/open-runs")]',
        '[HttpGet("me/open-runs/{openRunId}")]',
        '[HttpPost("me/workspaces/{workspaceId}/open-runs")]',
        '[HttpPost("me/open-runs/{openRunId}/join-requests")]',
        '[HttpPost("me/open-runs/{openRunId}/join-requests/{requestId}/reviews")]',
        '[HttpPost("me/open-runs/{openRunId}/schedule")]',
        '[HttpPost("me/open-runs/{openRunId}/meeting-handoff")]',
        '[HttpPost("me/open-runs/{openRunId}/closeout")]',
    ],
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs": [
        "public IReadOnlyList<OpenRunListingProjection> GetOpenRuns(",
        "public OpenRunOrchestrationProjection? GetOpenRun(",
        "public OpenRunListingProjection CreateOpenRun(",
        "public OpenRunJoinRequestProjection SubmitOpenRunJoinRequest(",
        "public OpenRunScheduleReceiptProjection ScheduleOpenRun(",
        "public OpenRunMeetingHandoffProjection CreateOpenRunMeetingHandoff(",
        "public OpenRunCloseoutProjection CloseOutOpenRun(",
        'Source kind: {OpenRunListingSourceKind}.',
        'Source kind: {OpenRunCloseoutSourceKind}.',
    ],
    "Chummer.Tests/OpenRunServiceTests.cs": [
        "public void OpenRunLoopPersistsListingJoinScheduleHandoffAndCloseout()",
        'ListingTitle: "Tacoma docks night extraction"',
        'Decision: "accepted"',
        'ProviderKind: "discord_event"',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        "var openRunCreateResult = await campaignSpineController.CreateMyCampaignWorkspaceOpenRun(",
        "var openRunJoinRequestResult = await openRunOutsiderController.SubmitMyOpenRunJoinRequest(",
        "var openRunScheduleResult = await campaignSpineController.ScheduleMyOpenRun(",
        "var openRunMeetingHandoffResult = await campaignSpineController.CreateMyOpenRunMeetingHandoff(",
        "var openRunCloseoutResult = await campaignSpineController.CloseOutMyOpenRun(",
        "campaign spine open-run orchestration should preserve the world-memory bridge across reload.",
    ],
    "scripts/materialize_next90_m123_hub_open_run_loop_proof.py": [
        '"package_id": "next90-m123-hub-build-openrun-listing-join-request-roster-schedule-meeti"',
        '"frontier_id": 8531582567',
        '"owned_surfaces": ["build_openrun_listing_join_request:hub"]',
    ],
    "scripts/verify_next90_m123_hub_open_run_loop.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        'print("next90 m123 hub open-run loop proof passed")',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/materialize_next90_m123_hub_open_run_loop_proof.py",
        "python3 scripts/verify_next90_m123_hub_open_run_loop.py",
        "python3 -m unittest tests/test_next90_m123_hub_open_run_loop.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M123_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M123_QUEUE_STAGING", "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
DESIGN_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M123_DESIGN_QUEUE_STAGING", "/docker/chummercomplete/chummer-design-m114/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
PROOF_PATH = ROOT / '.codex-studio' / 'published' / 'NEXT90_M123_HUB_OPEN_RUN_LOOP.generated.json'


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def load_yaml(path: Path) -> object:
    text = path.read_text(encoding='utf-8')
    return yaml.safe_load(text)


def load_queue_staging_yaml(path: Path) -> object:
    text = path.read_text(encoding='utf-8')
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        payload = None
    else:
        if isinstance(payload, dict) and isinstance(payload.get('items'), list):
            return payload

    package_marker = f'package_id: {PACKAGE_ID}'
    package_index = text.find(package_marker)
    if package_index < 0:
        raise ValueError(f'queue staging is missing package_id {PACKAGE_ID}')

    start = text.rfind('\n- title:', 0, package_index)
    if start < 0:
        if not text.startswith('- title:'):
            raise ValueError(f'queue staging is missing the item block for {PACKAGE_ID}')
        start = 0
    else:
        start += 1

    end = text.find('\n- title:', package_index)
    if end < 0:
        end = len(text)

    block = text[start:end].rstrip() + '\n'
    payload = yaml.safe_load(block)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError(f'queue staging package block for {PACKAGE_ID} must parse to exactly one item')
    return {'items': payload}


def verify_queue(path: Path, missing: list[str]) -> None:
    if not path.is_file():
        missing.append(f"missing queue staging file: {path}")
        return
    try:
        payload = load_queue_staging_yaml(path) or {}
    except (ValueError, yaml.YAMLError) as exc:
        missing.append(f"{path}: unable to load queue staging for {PACKAGE_ID}: {exc}")
        return
    items = payload.get('items') if isinstance(payload, dict) else None
    if not isinstance(items, list):
        missing.append(f"{path}: items is missing")
        return
    matches = [item for item in items if isinstance(item, dict) and item.get('package_id') == PACKAGE_ID]
    if len(matches) != 1:
        missing.append(f"{path}: expected exactly one {PACKAGE_ID} row, found {len(matches)}")
        return
    item = matches[0]
    expected = {
        'title': PACKAGE_TITLE,
        'task': PACKAGE_TASK,
        'repo': PACKAGE_REPO,
        'milestone_id': MILESTONE_ID,
        'work_task_id': WORK_TASK_ID,
        'frontier_id': FRONTIER_ID,
        'wave': PACKAGE_WAVE,
        'status': PACKAGE_STATUS,
        'allowed_paths': ALLOWED_PATHS,
        'owned_surfaces': OWNED_SURFACES,
    }
    for key, value in expected.items():
        if item.get(key) != value:
            missing.append(f"{path}: {PACKAGE_ID} {key} must be {value!r}")


def main() -> int:
    missing: list[str] = []
    verify_queue(FLEET_QUEUE_STAGING_PATH, missing)
    verify_queue(DESIGN_QUEUE_STAGING_PATH, missing)

    for relative_path, markers in SOURCE_MARKERS.items():
        text = read_text(relative_path)
        for marker in markers:
            if marker not in text:
                missing.append(f"{relative_path}: missing marker {marker}")
        if relative_path != "scripts/verify_next90_m123_hub_open_run_loop.py":
            for forbidden in FORBIDDEN_PROOF_MARKERS:
                if forbidden in text:
                    missing.append(f"{relative_path}: forbidden marker {forbidden}")

    materializer = ROOT / 'scripts' / 'materialize_next90_m123_hub_open_run_loop_proof.py'
    result = subprocess.run(["python3", str(materializer)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        missing.append(result.stderr.strip() or result.stdout.strip() or "materializer failed")
    elif not PROOF_PATH.is_file():
        missing.append(f"proof file was not written: {PROOF_PATH}")
    else:
        payload = json.loads(PROOF_PATH.read_text(encoding='utf-8'))
        if payload.get('package_proof', {}).get('package_id') != PACKAGE_ID:
            missing.append('proof file package_id drifted')

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("next90 m123 hub open-run loop proof passed")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
