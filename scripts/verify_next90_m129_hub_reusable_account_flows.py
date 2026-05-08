#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m129-hub-build-reusable-account-profile-group-membership-join-cod"
WORK_TASK_ID = "129.1"
FRONTIER_ID = 1246056730
MILESTONE_ID = 129
PACKAGE_TITLE = "Build reusable account, profile, group, membership, join-code, boost-code, reward-journal, and entitlement-journal flows."
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W19"
PACKAGE_STATUS = "not_started"
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["build_reusable_account_profile_group:hub"]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "supervisor status",
    "task-local telemetry",
]

SOURCE_MARKERS = {
    "Chummer.Run.Api/Contracts/ReusableAccountFlowContracts.cs": [
        "public sealed record ReusableAccountFlowContext(",
        "public sealed record ReusableAccountFlowBundle(",
        "public sealed record ReusableAccountFlowProjection(",
    ],
    "Chummer.Run.Api/Services/Community/ReusableAccountFlowService.cs": [
        "public sealed class ReusableAccountFlowService",
        'SurfaceId: "account_profile"',
        'SurfaceId: "group_profile"',
        'SurfaceId: "membership_status"',
        'SurfaceId: "join_code"',
        'SurfaceId: "boost_code"',
        'SurfaceId: "reward_journal"',
        'SurfaceId: "entitlement_journal"',
    ],
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs": [
        "services.AddSingleton<ReusableAccountFlowService>();",
    ],
    "Chummer.Tests/ReusableAccountFlowServiceTests.cs": [
        "public void ReusableAccountFlowCoversAccountGroupMembershipJoinBoostRewardAndEntitlementJournals()",
        'Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "account_profile", StringComparison.Ordinal)',
        'Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "entitlement_journal", StringComparison.Ordinal)',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        'var reusableAccountFlows = new ReusableAccountFlowService(releases).Build(new ReusableAccountFlowContext(',
        'community reusable account flow should keep reward-journal followthrough on the signed-in rewards rail.',
        'community reusable account flow should keep entitlement-journal followthrough on the signed-in entitlements rail.',
    ],
    "scripts/materialize_next90_m129_hub_reusable_account_flows_proof.py": [
        '"package_id": "next90-m129-hub-build-reusable-account-profile-group-membership-join-cod"',
        '"frontier_id": 1246056730',
        '"owned_surfaces": ["build_reusable_account_profile_group:hub"]',
    ],
    "scripts/verify_next90_m129_hub_reusable_account_flows.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        'print("next90 m129 hub reusable account flows proof passed")',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/materialize_next90_m129_hub_reusable_account_flows_proof.py",
        "python3 scripts/verify_next90_m129_hub_reusable_account_flows.py",
        "python3 -m unittest tests/test_next90_m129_hub_reusable_account_flows.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M129_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M129_QUEUE_STAGING", "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
DESIGN_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M129_DESIGN_QUEUE_STAGING", "/docker/chummercomplete/chummer-design-m114/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
PROOF_PATH = ROOT / ".codex-studio" / "published" / "NEXT90_M129_HUB_REUSABLE_ACCOUNT_FLOWS.generated.json"


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def load_yaml(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text)


def load_queue_staging_yaml(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        payload = None
    else:
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return payload

    package_marker = f"package_id: {PACKAGE_ID}"
    package_index = text.find(package_marker)
    if package_index < 0:
        raise ValueError(f"queue staging is missing package_id {PACKAGE_ID}")

    start = text.rfind("\n- title:", 0, package_index)
    if start < 0:
        if not text.startswith("- title:"):
            raise ValueError(f"queue staging is missing the item block for {PACKAGE_ID}")
        start = 0
    else:
        start += 1

    end = text.find("\n- title:", package_index)
    if end < 0:
        end = len(text)

    block = text[start:end].rstrip() + "\n"
    payload = yaml.safe_load(block)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError(f"queue staging package block for {PACKAGE_ID} must parse to exactly one item")
    return {"items": payload}


def verify_queue(path: Path, missing: list[str]) -> None:
    if not path.is_file():
        missing.append(f"missing queue staging file: {path}")
        return
    try:
        payload = load_queue_staging_yaml(path) or {}
    except (ValueError, yaml.YAMLError) as exc:
        missing.append(f"{path}: unable to load queue staging for {PACKAGE_ID}: {exc}")
        return
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        missing.append(f"{path}: items is missing")
        return
    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        missing.append(f"{path}: expected exactly one {PACKAGE_ID} row, found {len(matches)}")
        return
    item = matches[0]
    expected = {
        "title": PACKAGE_TITLE,
        "task": PACKAGE_TITLE,
        "repo": PACKAGE_REPO,
        "milestone_id": MILESTONE_ID,
        "work_task_id": WORK_TASK_ID,
        "frontier_id": FRONTIER_ID,
        "wave": PACKAGE_WAVE,
        "status": PACKAGE_STATUS,
        "allowed_paths": ALLOWED_PATHS,
        "owned_surfaces": OWNED_SURFACES,
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
        if relative_path != "scripts/verify_next90_m129_hub_reusable_account_flows.py":
            for forbidden in FORBIDDEN_PROOF_MARKERS:
                if forbidden in text:
                    missing.append(f"{relative_path}: forbidden marker {forbidden}")

    materializer = ROOT / "scripts" / "materialize_next90_m129_hub_reusable_account_flows_proof.py"
    result = subprocess.run(["python3", str(materializer)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        missing.append(result.stderr.strip() or result.stdout.strip() or "materializer failed")
    elif not PROOF_PATH.is_file():
        missing.append(f"proof file was not written: {PROOF_PATH}")
    else:
        payload = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
        if payload.get("package_proof", {}).get("package_id") != PACKAGE_ID:
            missing.append("proof file package_id drifted")

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("next90 m129 hub reusable account flows proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
