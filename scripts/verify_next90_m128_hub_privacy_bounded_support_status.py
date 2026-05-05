#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m128-hub-implement-privacy-bounded-support-crash-feedback-telemet"
WORK_TASK_ID = "128.4"
FRONTIER_ID = 4025965979
MILESTONE_ID = 128
PACKAGE_TITLE = "Implement privacy-bounded support, crash, feedback, telemetry rollups, retention clocks, and case-status followthrough."
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W18"
PACKAGE_STATUS = "not_started"
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["implement_privacy_bounded_support_crash:hub"]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "supervisor status",
    "task-local telemetry",
]

SOURCE_MARKERS = {
    "Chummer.Run.Api/Contracts/PrivacyBoundedSupportStatusContracts.cs": [
        "public sealed record PrivacyBoundedSupportStatusContext(",
        "public sealed record PrivacyBoundedSupportStatusBundle(",
        "public sealed record PrivacyBoundedSupportStatusProjection(",
    ],
    "Chummer.Run.Api/Services/Support/PrivacyBoundedSupportStatusService.cs": [
        "public sealed class PrivacyBoundedSupportStatusService",
        'SurfaceId: "support_status"',
        'SurfaceId: "crash_status"',
        'SurfaceId: "feedback_status"',
        'SurfaceId: "telemetry_rollup"',
        'SurfaceId: "retention_clocks"',
        'SurfaceId: "case_status_followthrough"',
    ],
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs": [
        "services.AddSingleton<PrivacyBoundedSupportStatusService>();",
    ],
    "Chummer.Tests/PrivacyBoundedSupportStatusServiceTests.cs": [
        "public void PrivacyBoundedSupportStatusCoversSupportCrashFeedbackTelemetryRetentionAndFollowthrough()",
        'Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "support_status", StringComparison.Ordinal)',
        'Assert.Contains(bundle.Projections, item => string.Equals(item.SurfaceId, "case_status_followthrough", StringComparison.Ordinal)',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        'var privacyBoundedSupportStatus = new PrivacyBoundedSupportStatusService(releases, new SupportConciergePacketService(releases, new SupportCasePresentationService())).Build(new PrivacyBoundedSupportStatusContext(',
        'campaign spine privacy-bounded support status should keep telemetry rollups on the privacy-bounded progress route.',
        'campaign spine privacy-bounded support status should keep case-status followthrough on the tracked support rail.',
    ],
    "scripts/materialize_next90_m128_hub_privacy_bounded_support_status_proof.py": [
        '"package_id": "next90-m128-hub-implement-privacy-bounded-support-crash-feedback-telemet"',
        '"frontier_id": 4025965979',
        '"owned_surfaces": ["implement_privacy_bounded_support_crash:hub"]',
    ],
    "scripts/verify_next90_m128_hub_privacy_bounded_support_status.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        'print("next90 m128 hub privacy bounded support status proof passed")',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/materialize_next90_m128_hub_privacy_bounded_support_status_proof.py",
        "python3 scripts/verify_next90_m128_hub_privacy_bounded_support_status.py",
        "python3 -m unittest tests/test_next90_m128_hub_privacy_bounded_support_status.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M128_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M128_QUEUE_STAGING", "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
DESIGN_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M128_DESIGN_QUEUE_STAGING", "/docker/chummercomplete/chummer-design-m114/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
PROOF_PATH = ROOT / ".codex-studio" / "published" / "NEXT90_M128_HUB_PRIVACY_BOUNDED_SUPPORT_STATUS.generated.json"


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def load_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


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
        if relative_path != "scripts/verify_next90_m128_hub_privacy_bounded_support_status.py":
            for forbidden in FORBIDDEN_PROOF_MARKERS:
                if forbidden in text:
                    missing.append(f"{relative_path}: forbidden marker {forbidden}")

    materializer = ROOT / "scripts" / "materialize_next90_m128_hub_privacy_bounded_support_status_proof.py"
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

    print("next90 m128 hub privacy bounded support status proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
