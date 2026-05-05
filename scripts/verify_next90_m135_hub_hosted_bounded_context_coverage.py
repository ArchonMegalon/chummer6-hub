#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from yaml.error import YAMLError


PACKAGE_ID = "next90-m135-hub-close-hosted-bounded-context-campaign-account-support-pu"
WORK_TASK_ID = "135.4"
FRONTIER_ID = 1932284114
MILESTONE_ID = 135
PACKAGE_TITLE = "Close hosted bounded-context, campaign, account, support, public, community, and orchestration-boundary coverage."
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W22"
PACKAGE_STATUS = "not_started"
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["close_hosted_bounded_context_campaign:hub"]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "supervisor status",
    "task-local telemetry",
]

SOURCE_MARKERS = {
    "Chummer.Run.Api/Contracts/HostedBoundedContextCoverageContracts.cs": [
        "public sealed record HostedBoundedContextCoverageContext(",
        "public sealed record HostedBoundedContextCoverageBundle(",
        "public sealed record HostedBoundedContextCoverageProjection(",
    ],
    "Chummer.Run.Api/Services/Support/HostedBoundedContextCoverageService.cs": [
        "public sealed class HostedBoundedContextCoverageService",
        'SurfaceId: "public_context"',
        'SurfaceId: "account_context"',
        'SurfaceId: "community_context"',
        'SurfaceId: "campaign_context"',
        'SurfaceId: "support_context"',
        'SurfaceId: "orchestration_boundary"',
        'SurfaceId: "bounded_context_closure"',
    ],
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs": [
        "services.AddSingleton<HostedBoundedContextCoverageService>();",
    ],
    "Chummer.Tests/HostedBoundedContextCoverageServiceTests.cs": [
        "public void HostedBoundedContextCoverageKeepsPublicAccountCommunityCampaignSupportAndOrchestrationSeparate()",
        'Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "public_context", StringComparison.Ordinal)',
        'Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "bounded_context_closure", StringComparison.Ordinal)',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        'var boundedContextCoverage = new HostedBoundedContextCoverageService(releases).Build(new HostedBoundedContextCoverageContext(',
        'hub bounded-context coverage should keep public context proof on the guest-readable landing rail.',
        'hub bounded-context coverage should keep closure proof on the public progress rail.',
    ],
    "scripts/materialize_next90_m135_hub_hosted_bounded_context_coverage_proof.py": [
        '"package_id": "next90-m135-hub-close-hosted-bounded-context-campaign-account-support-pu"',
        '"frontier_id": 1932284114',
        '"owned_surfaces": ["close_hosted_bounded_context_campaign:hub"]',
    ],
    "scripts/verify_next90_m135_hub_hosted_bounded_context_coverage.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        'print("next90 m135 hub hosted bounded-context coverage proof passed")',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/materialize_next90_m135_hub_hosted_bounded_context_coverage_proof.py",
        "python3 scripts/verify_next90_m135_hub_hosted_bounded_context_coverage.py",
        "python3 -m unittest tests/test_next90_m135_hub_hosted_bounded_context_coverage.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M135_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M135_QUEUE_STAGING", "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
DESIGN_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M135_DESIGN_QUEUE_STAGING", "/docker/chummercomplete/chummer-design-m114/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
PROOF_PATH = ROOT / ".codex-studio" / "published" / "NEXT90_M135_HUB_HOSTED_BOUNDED_CONTEXT_COVERAGE.generated.json"


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def load_yaml(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    try:
        return yaml.safe_load(text)
    except YAMLError:
        marker = "\nmode: append\n"
        index = text.find(marker)
        if index == -1:
            raise
        return yaml.safe_load(text[index + 1 :])


def verify_queue(path: Path, missing: list[str]) -> None:
    if not path.is_file():
        missing.append(f"missing queue staging file: {path}")
        return
    payload = load_yaml(path) or {}
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
        if relative_path != "scripts/verify_next90_m135_hub_hosted_bounded_context_coverage.py":
            for forbidden in FORBIDDEN_PROOF_MARKERS:
                if forbidden in text:
                    missing.append(f"{relative_path}: forbidden marker {forbidden}")

    materializer = ROOT / "scripts" / "materialize_next90_m135_hub_hosted_bounded_context_coverage_proof.py"
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

    print("next90 m135 hub hosted bounded-context coverage proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
