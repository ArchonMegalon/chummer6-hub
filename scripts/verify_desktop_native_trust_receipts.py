#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED_SOURCE_MARKERS = {
    Path("Chummer.Run.Api/Controllers/InstallLinkingController.cs"): [
        '[HttpPost("continuation")]',
        "ResolveInstallationForGrant(request.InstallationId, request.AccessToken)",
        "DesktopInstallRail.BuildContinuationReceipt(releaseArtifact, manifest, recoveryMode: false)",
        "BuildNativeNextSafeAction(updateAvailable, leadSupportCase, continuation)",
        "SupportCases: supportCases",
    ],
    Path("Chummer.Run.Api/Services/DesktopInstallRail.cs"): [
        "Claim codes are a recovery fallback, not a browser redemption step.",
        "desktop app update lane",
        "previous installed copy",
        "Support follow-through stays on the same install rail",
    ],
    Path("Chummer.Run.Api/Services/Support/SupportCasePresentationService.cs"): [
        "BuildInstallReadiness(",
        "FixReadyOnLinkedInstall",
        "NeedsInstallUpdate",
        "Follow-up stays inside Account > Support and Devices & access for this signed-in install rail.",
    ],
    Path("Chummer.Run.Api/Controllers/PublicLandingController.cs"): [
        '"/downloads/install/{artifactId}/continue.json"',
        "DesktopInstallRail.BuildSupportHref(",
        "DesktopInstallRail.BuildContinuationReceipt(",
        "ResolveSupportIntakeRailFromQuery()",
    ],
    Path("Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml"): [
        "Automatic account linking is the default path. Use claim-code fallback only when Chummer explicitly says it is in recovery mode.",
        "Support follow-through stays on the same install rail",
    ],
    Path("tests/RunServicesVerification/InstallLinkingContinuationVerification.cs"): [
        "ContinueClaimedInstall(",
        "UpdateAvailable",
        "NeedsInstallUpdate",
        "Invalid desktop continuation grants should fail closed.",
    ],
}


REQUIRED_PROOF_RECEIPTS = {
    "desktop_native_claim_and_recovery": {
        "package_id": "next90-m102-hub-desktop-native-trust",
        "milestone_id": 102,
        "frontier_id": 2897065929,
        "surfaces": [
            "desktop_native_claim_and_recovery",
            "install_claim_restore_continue",
            "claimed_install_continuation",
        ],
        "routes": [
            "/downloads/install/avalonia-linux-x64-installer/continue.json",
            "/api/v1/install-linking/continuation",
            "/account/access",
        ],
    },
    "support_followthrough:install_truth": {
        "package_id": "next90-m102-hub-desktop-native-trust",
        "milestone_id": 102,
        "frontier_id": 2897065929,
        "surfaces": [
            "support_followthrough:install_truth",
            "support_case_install_readiness",
            "desktop_update_rollback_recovery",
        ],
        "routes": [
            "/api/v1/install-linking/continuation",
            "/account/support",
            "/contact",
        ],
    },
}


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    errors: list[str] = []

    for relative_path, markers in REQUIRED_SOURCE_MARKERS.items():
        path = repo_root / relative_path
        if not path.is_file():
            errors.append(f"missing source file: {relative_path}")
            continue

        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                errors.append(f"{relative_path} missing marker: {marker}")

    proof_path = repo_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
    if not proof_path.is_file():
        errors.append(f"missing proof file: {proof_path.relative_to(repo_root)}")
    else:
        try:
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"proof file is not valid json: {exc}")
        else:
            packages = proof.get("successor_queue_packages")
            if not isinstance(packages, list) or not any(
                isinstance(item, dict)
                and item.get("package_id") == "next90-m102-hub-desktop-native-trust"
                and item.get("milestone_id") == 102
                and item.get("frontier_id") == 2897065929
                for item in packages
            ):
                errors.append("proof missing successor_queue_packages entry for next90-m102-hub-desktop-native-trust")

            receipts = {
                item.get("receipt_id"): item
                for item in proof.get("proof_receipts", [])
                if isinstance(item, dict)
            }
            for receipt_id, expected in REQUIRED_PROOF_RECEIPTS.items():
                receipt = receipts.get(receipt_id)
                if not isinstance(receipt, dict):
                    errors.append(f"proof missing receipt: {receipt_id}")
                    continue

                for key in ("package_id", "milestone_id", "frontier_id"):
                    if receipt.get(key) != expected[key]:
                        errors.append(f"{receipt_id} has wrong {key}: {receipt.get(key)!r}")

                for key in ("surfaces", "routes"):
                    actual_values = receipt.get(key)
                    if not isinstance(actual_values, list):
                        errors.append(f"{receipt_id} missing list field: {key}")
                        continue

                    actual = {item for item in actual_values if isinstance(item, str)}
                    for required in expected[key]:
                        if required not in actual:
                            errors.append(f"{receipt_id} missing {key[:-1]}: {required}")

    if errors:
        print("desktop native trust receipt verification failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("desktop native trust receipts verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
