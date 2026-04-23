#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m111-hub-support-concierge"
FRONTIER_ID = 2746902416
MILESTONE_ID = 111
OWNED_SURFACES = ["install_aware_support_concierge", "release_concierge:hub"]
DESIGN_OWNED_SURFACES = [*OWNED_SURFACES, "public_concierge_wrapper:hub"]
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_SUPPORT_CONCIERGE_ROOT", DEFAULT_ROOT))
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_SUPPORT_CONCIERGE_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_SUPPORT_CONCIERGE_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_SUPPORT_CONCIERGE_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)

SOURCE_MARKERS: dict[str, list[str]] = {
    "Chummer.Run.Api/Services/Support/SupportConciergePacketService.cs": [
        f'private const string PackageId = "{PACKAGE_ID}";',
        f"private const int MilestoneId = {MILESTONE_ID};",
        f"private const long FrontierId = {FRONTIER_ID};",
        'ContractName: "chummer6-hub.install_aware_support_concierge.v1"',
        "InstalledBuildTruth: installedTruth",
        "ReleaseTruth: releaseTruth",
        "SupportCaseTruth: supportTruth",
        "SupportClosure: new SupportClosureConciergePacket(",
        "ReleaseExplainer: new ReleaseExplainerConciergePacket(",
        "PublicTrustWrapper: new PublicConciergeTrustWrapper(",
        "FirstPartyOnlyTruth: true",
        "Installed build receipt:",
        "ChannelAgreesWithInstalledBuild: channelAgrees",
        "support_case+claimed_install",
        '"/api/v1/support/cases/{Uri.EscapeDataString(supportCase.CaseId)}/concierge"',
        '"/api/v1/install-linking/continuation/support"',
        '"/contact#support-intake"',
        'route.StartsWith("/contact", StringComparison.OrdinalIgnoreCase)',
        "public sealed record InstallAwareSupportConciergePacket(",
        "public sealed record InstallAwareBuildTruth(",
        "public sealed record InstallAwareReleaseTruth(",
        "public sealed record SupportCaseConciergeTruth(",
    ],
    "Chummer.Run.Api/Controllers/SupportCasesController.cs": [
        "private readonly SupportConciergePacketService _supportConciergePackets;",
        '[HttpGet("{caseId}/concierge")]',
        "[ProducesResponseType<InstallAwareSupportConciergePacket>(StatusCodes.Status200OK)]",
        "_supportConciergePackets.Build(item, installLinking)",
        "_installLinking.GetSummary(user.UserId, subject.SubjectId)",
    ],
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs": [
        "services.AddSingleton<SupportConciergePacketService>();",
    ],
    "tests/RunServicesVerification/SupportCrashVerification.cs": [
        "SupportConciergePacketService conciergePackets",
        "InstallAwareSupportConciergePacket conciergePacket = conciergePackets.Build(",
        'VerificationAssert.Equal("chummer6-hub.install_aware_support_concierge.v1"',
        'VerificationAssert.Equal("next90-m111-hub-support-concierge"',
        "conciergePacket.IsInstallAware",
        "conciergePacket.InstalledBuildTruth.InstalledBuildReceiptId",
        "conciergePacket.ReleaseTruth.CurrentArtifactId",
        "conciergePacket.ReleaseExplainer.CorrectnessBasis.Contains",
        "conciergePacket.PublicTrustWrapper.FirstPartyOnlyTruth",
    ],
    "scripts/materialize_hub_local_release_proof.py": [
        f'"package_id": "{PACKAGE_ID}"',
        f'"frontier_id": {FRONTIER_ID}',
        '"install_aware_support_concierge"',
        '"release_concierge:hub"',
        '"/api/v1/support/cases/{caseId}/concierge"',
        '"/downloads/install/{artifactId}"',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_install_aware_support_concierge.py",
        "python3 -m unittest tests/test_install_aware_support_concierge.py",
    ],
}


def main() -> int:
    missing: list[str] = []
    for relative_path, markers in SOURCE_MARKERS.items():
        path = ROOT / relative_path
        if not path.is_file():
            missing.append(f"missing file: {relative_path}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                missing.append(f"{relative_path}: missing marker {marker!r}")

    verify_queue_authority(
        missing,
        QUEUE_STAGING_PATH,
        "Fleet queue",
        expected_title="Emit install-aware release and support concierge packets from installed-build truth",
        expected_task="Compile support closure and release explainer packets from installed build, channel, and support-case truth.",
        expected_owned_surfaces=OWNED_SURFACES,
    )
    verify_queue_authority(
        missing,
        DESIGN_QUEUE_STAGING_PATH,
        "design queue",
        expected_title="Emit install-aware release, support, and public concierge packets from installed-build truth",
        expected_task="Compile support closure and release explainer packets, plus public trust wrapper flows with first-party fallbacks, from installed build, channel, and support-case truth.",
        expected_owned_surfaces=DESIGN_OWNED_SURFACES,
    )
    verify_successor_registry(missing, SUCCESSOR_REGISTRY_PATH)

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("install-aware support concierge proof passed")
    return 0


def verify_queue_authority(
    missing: list[str],
    path: Path,
    label: str,
    *,
    expected_title: str,
    expected_task: str,
    expected_owned_surfaces: list[str],
) -> None:
    if not path.is_file():
        missing.append(f"{label} is missing: {path}")
        return
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = payload.get("items")
    if not isinstance(items, list):
        missing.append(f"{label} items must be a list: {path}")
        return
    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        missing.append(f"{label} must contain exactly one {PACKAGE_ID} row: {path}")
        return
    item = matches[0]
    expected = {
        "repo": "chummer6-hub",
        "milestone_id": MILESTONE_ID,
        "wave": "W9",
        "title": expected_title,
        "task": expected_task,
    }
    for key, value in expected.items():
        if item.get(key) != value:
            missing.append(f"{label} {PACKAGE_ID} {key} must be {value!r}: {path}")
    if "frontier_id" in item and item.get("frontier_id") != FRONTIER_ID:
        missing.append(f"{label} {PACKAGE_ID} frontier_id must be {FRONTIER_ID}: {path}")
    if "status" in item and item.get("status") not in {"in_progress", "complete"}:
        missing.append(f"{label} {PACKAGE_ID} status must be 'in_progress' or 'complete': {path}")
    if item.get("allowed_paths") != ALLOWED_PATHS:
        missing.append(f"{label} {PACKAGE_ID} allowed_paths drifted: {path}")
    if item.get("owned_surfaces") != expected_owned_surfaces:
        missing.append(f"{label} {PACKAGE_ID} owned_surfaces drifted: {path}")


def verify_successor_registry(missing: list[str], path: Path) -> None:
    if not path.is_file():
        missing.append(f"successor registry is missing: {path}")
        return
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    milestones = payload.get("milestones")
    if not isinstance(milestones, list):
        missing.append(f"successor registry milestones must be a list: {path}")
        return
    matches = [item for item in milestones if isinstance(item, dict) and item.get("id") == MILESTONE_ID]
    if len(matches) != 1:
        missing.append(f"successor registry must contain exactly one milestone {MILESTONE_ID}: {path}")
        return
    milestone = matches[0]
    if milestone.get("title") != "Install-aware release, support, and public concierge":
        missing.append(f"successor registry milestone {MILESTONE_ID} title drifted: {path}")
    tasks = milestone.get("work_tasks")
    if not isinstance(tasks, list):
        missing.append(f"successor registry milestone {MILESTONE_ID} work_tasks must be a list: {path}")
        return
    task_matches = [
        item
        for item in tasks
        if isinstance(item, dict)
        and item.get("id") == 111.1
        and item.get("owner") == "chummer6-hub"
    ]
    if len(task_matches) != 1:
        missing.append(f"successor registry must contain exactly one chummer6-hub work task 111.1: {path}")
        return
    title = str(task_matches[0].get("title") or "")
    if "Emit install-aware support and release concierge packets" not in title:
        missing.append(f"successor registry task 111.1 title drifted: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
