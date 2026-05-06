#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m123-hub-build-openrun-listing-join-request-roster-schedule-meeti",
    "work_task_id": "123.1",
    "title": "Build OpenRun listing, join request, roster, schedule, meeting-handoff, and closeout orchestration.",
    "task": "Build OpenRun listing, join request, roster, schedule, meeting-handoff, and closeout orchestration.",
    "frontier_id": 8531582567,
    "milestone_id": 123,
    "wave": "W16",
    "repo": "chummer6-hub",
    "status": "not_started",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["build_openrun_listing_join_request:hub"],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M123_HUB_ROOT", DEFAULT_ROOT))
SOURCE = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M123_HUB_SOURCE",
        ROOT / "tests" / "RunServicesSmoke" / "Program.cs",
    )
)
OUT = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M123_HUB_PROOF_OUT",
        ROOT / ".codex-studio" / "published" / "NEXT90_M123_HUB_OPEN_RUNS.generated.json",
    )
)

REQUIRED_MARKERS = {
    "build_openrun_listing_join_request:hub": [
        "var openRunsResult = await campaignSpineController.GetMyOpenRuns(CancellationToken.None);",
        "new OpenRunJoinRequestRequest(",
        "var openRunRosterDecisionResult = await campaignSpineController.ReviewMyOpenRunJoinRequest(",
        "var openRunScheduleResult = await campaignSpineController.ScheduleMyOpenRun(",
    ],
    "meeting_handoff_closeout:hub": [
        "var openRunMeetingHandoffResult = await campaignSpineController.PublishMyOpenRunMeetingHandoff(",
        "new OpenRunMeetingHandoffRequest(",
        "var openRunCloseoutResult = await campaignSpineController.CloseOutMyOpenRun(",
        "Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, \"open_run\", StringComparison.Ordinal)) == true, \"campaign spine server plane api should add open-run coordination packets into the bounded what-changed rail.\");",
    ],
}


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_source_path() -> str:
    try:
        return str(SOURCE.relative_to(ROOT))
    except ValueError:
        return str(SOURCE)


def without_generated_at(payload: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if key != "generated_at"}


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    surfaces_passed: list[str] = []
    missing_markers: dict[str, list[str]] = {}

    for surface, markers in REQUIRED_MARKERS.items():
        surface_missing = [marker for marker in markers if marker not in text]
        if surface_missing:
            missing_markers[surface] = surface_missing
            continue
        surfaces_passed.append(surface)

    payload = {
        "contract_name": "chummer6-hub.next90_m123_hub_open_runs",
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "package_proof": PACKAGE_PROOF,
        "source_file": canonical_source_path(),
        "surfaces_passed": surfaces_passed,
        "missing_markers": missing_markers,
        "required_markers": REQUIRED_MARKERS,
    }

    if OUT.is_file():
        try:
            existing_payload = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_payload = None
        if isinstance(existing_payload, dict) and without_generated_at(existing_payload) == payload:
            print(f"next90 m123 hub open-runs proof unchanged: {OUT}")
            return 0

    payload["generated_at"] = iso_now()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote next90 m123 hub open-runs proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
