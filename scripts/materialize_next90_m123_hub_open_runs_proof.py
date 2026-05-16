#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
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
OUT = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M123_HUB_PROOF_OUT",
        ROOT / ".codex-studio" / "published" / "NEXT90_M123_HUB_OPEN_RUNS.generated.json",
    )
)
LOOP_MATERIALIZER = ROOT / "scripts" / "materialize_next90_m123_hub_open_run_loop_proof.py"
LOOP_PROOF = ROOT / ".codex-studio" / "published" / "NEXT90_M123_HUB_OPEN_RUN_LOOP.generated.json"


def main() -> int:
    if not LOOP_MATERIALIZER.is_file():
        print(f"missing delegated materializer: {LOOP_MATERIALIZER}", file=sys.stderr)
        return 1

    result = subprocess.run(
        ["python3", str(LOOP_MATERIALIZER)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip() or "delegated materializer failed", file=sys.stderr)
        return 1

    if not LOOP_PROOF.is_file():
        print(f"delegated proof file was not written: {LOOP_PROOF}", file=sys.stderr)
        return 1

    delegated_payload = json.loads(LOOP_PROOF.read_text(encoding="utf-8"))
    payload = {
        "contract_name": "chummer6-hub.next90_m123_hub_open_runs",
        "status": "superseded_by_open_run_loop",
        "proof_kind": "compatibility_redirect",
        "package_proof": PACKAGE_PROOF,
        "source_file": delegated_payload.get("source_file", "tests/RunServicesSmoke/Program.cs"),
        "superseded_by": {
            "contract_name": "chummer6-hub.next90_m123_hub_open_run_loop",
            "proof_file": ".codex-studio/published/NEXT90_M123_HUB_OPEN_RUN_LOOP.generated.json",
            "materializer": "scripts/materialize_next90_m123_hub_open_run_loop_proof.py",
            "verifier": "scripts/verify_next90_m123_hub_open_run_loop.py",
            "test": "tests/test_next90_m123_hub_open_run_loop.py",
        },
        "delegated_contract": {
            "contract_name": delegated_payload.get("contract_name"),
            "status": delegated_payload.get("status"),
            "proof_kind": delegated_payload.get("proof_kind"),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote next90 m123 hub open-runs compatibility proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
