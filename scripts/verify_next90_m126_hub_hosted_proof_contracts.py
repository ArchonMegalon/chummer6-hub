#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m126-hub-define-hosted-proof-contracts-for-open-runs-shadowcaster"
WORK_TASK_ID = "126.4"
FRONTIER_ID = 6966685835
MILESTONE_ID = 126
FLEET_PACKAGE_TITLE = "Define hosted proof contracts for Open Runs, Shadowcasters, public signal, community, and account-aware horizon conversions."
DESIGN_PACKAGE_TITLE = "Define hosted proof contracts for Open Runs, Community Hub, public signal, community, and account-aware horizon conversions."
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W17"
PACKAGE_STATUS = "not_started"
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["define_hosted_proof_contracts_for:hub"]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "supervisor status",
    "task-local telemetry",
]

SOURCE_MARKERS = {
    "Chummer.Run.Api/Contracts/HostedProofContractContracts.cs": [
        "public sealed record HostedProofContractContext(",
        "public sealed record HostedProofContractBundle(",
        "public sealed record HostedProofContractProjection(",
    ],
    "Chummer.Run.Api/Services/Support/HostedProofContractService.cs": [
        "public sealed class HostedProofContractService",
        'ContractName: "open_runs_hosted_proof_contract"',
        'ContractName: "shadowcasters_horizon_hosted_proof_contract"',
        'ContractName: "public_signal_hosted_proof_contract"',
        'ContractName: "community_hub_hosted_proof_contract"',
        'ContractName: "account_aware_horizon_conversion_hosted_proof_contract"',
    ],
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs": [
        "services.AddSingleton<HostedProofContractService>();",
    ],
    "Chummer.Tests/HostedProofContractServiceTests.cs": [
        "public void HostedProofContractsCoverOpenRunsShadowcastersPublicSignalCommunityAndAccountAwareHorizonConversion()",
        'Assert.Contains(bundle.Contracts, item => string.Equals(item.SurfaceId, "open_runs", StringComparison.Ordinal)',
        'Assert.Contains(bundle.Contracts, item => string.Equals(item.SurfaceId, "account_aware_horizon_conversion", StringComparison.Ordinal)',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        'var hostedProofContracts = new HostedProofContractService(releases).Build(new HostedProofContractContext(',
        'campaign spine hosted proof contracts should emit open-run proof on the governed open-run route.',
        'campaign spine hosted proof contracts should emit account-aware horizon conversion proof on the Devices & access route.',
    ],
    "scripts/materialize_next90_m126_hub_hosted_proof_contracts_proof.py": [
        '"package_id": "next90-m126-hub-define-hosted-proof-contracts-for-open-runs-shadowcaster"',
        '"frontier_id": 6966685835',
        '"owned_surfaces": ["define_hosted_proof_contracts_for:hub"]',
    ],
    "scripts/verify_next90_m126_hub_hosted_proof_contracts.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        'print("next90 m126 hub hosted proof contracts proof passed")',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/materialize_next90_m126_hub_hosted_proof_contracts_proof.py",
        "python3 scripts/verify_next90_m126_hub_hosted_proof_contracts.py",
        "python3 -m unittest tests/test_next90_m126_hub_hosted_proof_contracts.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M126_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M126_QUEUE_STAGING", "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
DESIGN_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M126_DESIGN_QUEUE_STAGING", "/docker/chummercomplete/chummer-design-m114/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
PROOF_PATH = ROOT / ".codex-studio" / "published" / "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json"


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def load_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def verify_queue(path: Path, missing: list[str], *, expected_title: str) -> None:
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
        "title": expected_title,
        "task": expected_title,
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
    verify_queue(FLEET_QUEUE_STAGING_PATH, missing, expected_title=FLEET_PACKAGE_TITLE)
    verify_queue(DESIGN_QUEUE_STAGING_PATH, missing, expected_title=DESIGN_PACKAGE_TITLE)

    for relative_path, markers in SOURCE_MARKERS.items():
        text = read_text(relative_path)
        for marker in markers:
            if marker not in text:
                missing.append(f"{relative_path}: missing marker {marker}")
        if relative_path != "scripts/verify_next90_m126_hub_hosted_proof_contracts.py":
            for forbidden in FORBIDDEN_PROOF_MARKERS:
                if forbidden in text:
                    missing.append(f"{relative_path}: forbidden marker {forbidden}")

    materializer = ROOT / "scripts" / "materialize_next90_m126_hub_hosted_proof_contracts_proof.py"
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

    print("next90 m126 hub hosted proof contracts proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
