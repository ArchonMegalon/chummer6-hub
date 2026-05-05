#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m127-hub-keep-downloads-install-help-account-aware-guidance-suppo"
WORK_TASK_ID = "127.3"
FRONTIER_ID = 6974083833
MILESTONE_ID = 127
PACKAGE_TITLE = "Keep downloads, install help, account-aware guidance, support recovery, and public release shelf UX bound to registry truth."
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W18"
PACKAGE_STATUS = "not_started"
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["keep_downloads_install_help_account:hub"]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "supervisor status",
    "task-local telemetry",
]

SOURCE_MARKERS = {
    "Chummer.Run.Api/Contracts/RegistryTruthBindingContracts.cs": [
        "public sealed record RegistryTruthBindingContext(",
        "public sealed record RegistryTruthBindingBundle(",
        "public sealed record RegistryTruthBindingProjection(",
    ],
    "Chummer.Run.Api/Services/Support/RegistryTruthBindingService.cs": [
        "public sealed class RegistryTruthBindingService",
        'SurfaceId: "downloads"',
        'SurfaceId: "install_help"',
        'SurfaceId: "account_aware_guidance"',
        'SurfaceId: "support_recovery"',
        'SurfaceId: "public_release_shelf"',
    ],
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs": [
        "services.AddSingleton<RegistryTruthBindingService>();",
    ],
    "Chummer.Tests/RegistryTruthBindingServiceTests.cs": [
        "public void RegistryTruthBindingsCoverDownloadsInstallHelpAccountAwareGuidanceSupportRecoveryAndPublicShelf()",
        'Assert.Contains(bundle.Bindings, item => string.Equals(item.SurfaceId, "downloads", StringComparison.Ordinal)',
        'Assert.Contains(bundle.Bindings, item => string.Equals(item.SurfaceId, "public_release_shelf", StringComparison.Ordinal)',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        'var registryTruthBindings = new RegistryTruthBindingService(releases, new SupportConciergePacketService(releases, new SupportCasePresentationService())).Build(new RegistryTruthBindingContext(',
        'campaign spine registry truth bindings should keep downloads on the registry-backed shelf.',
        'campaign spine registry truth bindings should keep the public release shelf on the registry-backed current-release route.',
    ],
    "scripts/materialize_next90_m127_hub_registry_truth_binding_proof.py": [
        '"package_id": "next90-m127-hub-keep-downloads-install-help-account-aware-guidance-suppo"',
        '"frontier_id": 6974083833',
        '"owned_surfaces": ["keep_downloads_install_help_account:hub"]',
    ],
    "scripts/verify_next90_m127_hub_registry_truth_binding.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        'print("next90 m127 hub registry truth binding proof passed")',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/materialize_next90_m127_hub_registry_truth_binding_proof.py",
        "python3 scripts/verify_next90_m127_hub_registry_truth_binding.py",
        "python3 -m unittest tests/test_next90_m127_hub_registry_truth_binding.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M127_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M127_QUEUE_STAGING", "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
DESIGN_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M127_DESIGN_QUEUE_STAGING", "/docker/chummercomplete/chummer-design-m114/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
PROOF_PATH = ROOT / ".codex-studio" / "published" / "NEXT90_M127_HUB_REGISTRY_TRUTH_BINDING.generated.json"


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
        if relative_path != "scripts/verify_next90_m127_hub_registry_truth_binding.py":
            for forbidden in FORBIDDEN_PROOF_MARKERS:
                if forbidden in text:
                    missing.append(f"{relative_path}: forbidden marker {forbidden}")

    materializer = ROOT / "scripts" / "materialize_next90_m127_hub_registry_truth_binding_proof.py"
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

    print("next90 m127 hub registry truth binding proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
