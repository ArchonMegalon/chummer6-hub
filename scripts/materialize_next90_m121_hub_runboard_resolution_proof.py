#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m121-hub-persist-session-turn-ledger-handoff-runboard-state-and-r",
    "work_task_id": "121.5",
    "title": "Persist session turn-ledger handoff, runboard state, and ResolutionReport draft continuity without owning engine math.",
    "task": "Persist session turn-ledger handoff, runboard state, and ResolutionReport draft continuity without owning engine math.",
    "frontier_id": 7165194744,
    "milestone_id": 121,
    "wave": "W15",
    "repo": "chummer6-hub",
    "status": "not_started",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["persist_session_turn_ledger_handoff:hub"],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M121_HUB_ROOT", DEFAULT_ROOT))
SOURCE = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M121_HUB_SOURCE",
        ROOT / "tests" / "RunServicesSmoke" / "Program.cs",
    )
)
OUT = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M121_HUB_PROOF_OUT",
        ROOT / ".codex-studio" / "published" / "NEXT90_M121_HUB_RUNBOARD_RESOLUTION.generated.json",
    )
)

REQUIRED_MARKERS = {
    "persist_session_turn_ledger_handoff:hub": [
        'PackageKind: "runboard_state",',
        'Assert(runboardStatePayload.EvidenceLines.Any(item => item.Contains("Turn ledger handoff:", StringComparison.OrdinalIgnoreCase)), "campaign spine runboard state api should persist turn-ledger handoff evidence lines.");',
        'Assert(runboardStatePayload.EvidenceLines.Any(item => item.Contains("Runboard state:", StringComparison.OrdinalIgnoreCase)), "campaign spine runboard state api should persist runboard-state evidence lines.");',
        'Assert(refreshedWorkspaceServerPlanePayload?.AftermathPackages.Any(item => string.Equals(item.PackageId, runboardStatePayload.PackageId, StringComparison.Ordinal)) == true, "campaign spine server plane api should project runboard state packets after generation.");',
        'Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "runboard_state", StringComparison.Ordinal)) == true, "campaign spine server plane api should name runboard packets explicitly on the bounded what-changed rail.");',
    ],
    "resolution_report_draft_continuity": [
        'PackageKind: "resolution_report_draft",',
        'Assert(resolutionReportDraftPayload.EvidenceLines.Any(item => item.Contains("Turn ledger handoff:", StringComparison.OrdinalIgnoreCase)), "campaign spine ResolutionReport draft api should persist turn-ledger handoff evidence lines.");',
        'Assert(resolutionReportDraftPayload.EvidenceLines.Any(item => item.Contains("ResolutionReport draft posture:", StringComparison.OrdinalIgnoreCase)), "campaign spine ResolutionReport draft api should persist draft-posture evidence lines.");',
        'Assert(refreshedWorkspaceServerPlanePayload?.AftermathPackages.Any(item => string.Equals(item.PackageId, resolutionReportDraftPayload.PackageId, StringComparison.Ordinal)) == true, "campaign spine server plane api should project ResolutionReport draft packets after generation.");',
        'Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "resolution_report", StringComparison.Ordinal)) == true, "campaign spine server plane api should name ResolutionReport drafts explicitly on the bounded what-changed rail.");',
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
    missing: list[str] = []
    surfaces_passed: list[str] = []

    for surface, markers in REQUIRED_MARKERS.items():
        surface_missing = [marker for marker in markers if marker not in text]
        if surface_missing:
            for marker in surface_missing:
                missing.append(f"{surface}: {marker}")
            continue
        surfaces_passed.append(surface)

    if missing:
        for item in missing:
            print(f"next90_m121_hub_runboard_resolution_missing: {item}", file=sys.stderr)
        return 1

    payload = {
        "contract_name": "chummer6-hub.next90_m121_hub_runboard_resolution",
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "package_proof": PACKAGE_PROOF,
        "source_file": canonical_source_path(),
        "surfaces_passed": surfaces_passed,
        "required_markers": REQUIRED_MARKERS,
    }

    if OUT.is_file():
        try:
            existing_payload = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_payload = None

        if isinstance(existing_payload, dict) and without_generated_at(existing_payload) == payload:
            print(f"next90 m121 hub runboard resolution proof unchanged: {OUT}")
            return 0

    payload["generated_at"] = iso_now()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote next90 m121 hub runboard resolution proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
