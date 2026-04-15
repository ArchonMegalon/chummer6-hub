#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PACKAGE_ID = "next90-m102-hub-desktop-native-trust"
LANDED_COMMIT = "160af58f"
FRONTIER_ID = 2897065929

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
        "frontier_id": FRONTIER_ID,
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
        "frontier_id": FRONTIER_ID,
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


REQUIRED_CANONICAL_QUEUE_MARKERS = [
    f"package_id: {PACKAGE_ID}",
    "milestone_id: 102",
    "repo: chummer6-hub",
    "status: complete",
    f"landed_commit: {LANDED_COMMIT}",
]

REQUIRED_CANONICAL_REGISTRY_MARKERS = [
    "id: 102.1",
    "owner: chummer6-hub",
    "status: complete",
    f"landed_commit: {LANDED_COMMIT}",
    PACKAGE_ID,
    "desktop_native_claim_and_recovery",
    "support_followthrough:install_truth",
]

REQUIRED_CANONICAL_QUEUE_LISTS = {
    "allowed_paths": [
        "Chummer.Run.Api",
        "scripts",
        "tests",
    ],
    "owned_surfaces": [
        "desktop_native_claim_and_recovery",
        "support_followthrough:install_truth",
    ],
}

REQUIRED_PROOF_PACKAGE = {
    "package_id": PACKAGE_ID,
    "milestone_id": 102,
    "frontier_id": FRONTIER_ID,
    "status": "complete",
    "landed_commit": LANDED_COMMIT,
    "allowed_paths": REQUIRED_CANONICAL_QUEUE_LISTS["allowed_paths"],
    "owned_surfaces": REQUIRED_CANONICAL_QUEUE_LISTS["owned_surfaces"],
}

DEFAULT_PROOF_PATH = Path(".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json")
DEFAULT_QUEUE_STAGING_PATH = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
DEFAULT_DESIGN_QUEUE_STAGING_PATH = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
DEFAULT_SUCCESSOR_REGISTRY_PATH = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml")


def _configured_path(env_name: str, default_path: Path) -> Path:
    override = os.environ.get(env_name)
    return Path(override) if override else default_path


def _proof_path(repo_root: Path) -> Path:
    configured = _configured_path("CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH", DEFAULT_PROOF_PATH)
    return configured if configured.is_absolute() else repo_root / configured


def _extract_yaml_block(text: str, anchor: str) -> str | None:
    start = text.find(anchor)
    if start < 0:
        return None

    next_item = text.find("\n  - ", start + len(anchor))
    return text[start:] if next_item < 0 else text[start:next_item]


def _verify_marker_block(
    errors: list[str],
    path: Path,
    anchor: str,
    markers: list[str],
    label: str,
    required_lists: dict[str, list[str]] | None = None,
) -> None:
    if not path.is_file():
        errors.append(f"missing canonical {label} file: {path}")
        return

    text = path.read_text(encoding="utf-8")
    block = _extract_yaml_block(text, anchor)
    if block is None:
        errors.append(f"canonical {label} missing block anchored by: {anchor}")
        return

    for marker in markers:
        if marker not in block:
            errors.append(f"canonical {label} block missing marker: {marker}")

    if required_lists is not None:
        for key, expected_values in required_lists.items():
            actual_values = _extract_yaml_string_list(block, key)
            if actual_values is None:
                errors.append(f"canonical {label} block missing list: {key}")
                continue

            if actual_values != expected_values:
                errors.append(
                    f"canonical {label} block has wrong {key}: "
                    f"expected {expected_values!r}, got {actual_values!r}"
                )


def _extract_yaml_string_list(block: str, key: str) -> list[str] | None:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != f"{key}:":
            continue

        values: list[str] = []
        list_indent: int | None = None
        for child in lines[index + 1 :]:
            stripped = child.strip()
            if not stripped:
                continue

            indent = len(child) - len(child.lstrip(" "))
            if list_indent is None:
                list_indent = indent
            elif indent < list_indent:
                break

            if not stripped.startswith("- "):
                break

            values.append(stripped[2:].strip())

        return values

    return None


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

    proof_path = _proof_path(repo_root)
    if not proof_path.is_file():
        try:
            display_path = proof_path.relative_to(repo_root)
        except ValueError:
            display_path = proof_path
        errors.append(f"missing proof file: {display_path}")
    else:
        try:
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"proof file is not valid json: {exc}")
        else:
            packages = proof.get("successor_queue_packages")
            proof_package = None
            if isinstance(packages, list):
                proof_package = next(
                    (
                        item
                        for item in packages
                        if isinstance(item, dict)
                        and item.get("package_id") == PACKAGE_ID
                    ),
                    None,
                )

            if not isinstance(proof_package, dict):
                errors.append("proof missing successor_queue_packages entry for next90-m102-hub-desktop-native-trust")
            else:
                for key, expected in REQUIRED_PROOF_PACKAGE.items():
                    actual = proof_package.get(key)
                    if actual != expected:
                        errors.append(f"proof package has wrong {key}: expected {expected!r}, got {actual!r}")

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

    _verify_marker_block(
        errors,
        _configured_path("CHUMMER_NEXT90_QUEUE_STAGING_PATH", DEFAULT_QUEUE_STAGING_PATH),
        f"package_id: {PACKAGE_ID}",
        REQUIRED_CANONICAL_QUEUE_MARKERS,
        "successor queue staging",
        REQUIRED_CANONICAL_QUEUE_LISTS,
    )
    _verify_marker_block(
        errors,
        _configured_path("CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH", DEFAULT_DESIGN_QUEUE_STAGING_PATH),
        f"package_id: {PACKAGE_ID}",
        REQUIRED_CANONICAL_QUEUE_MARKERS,
        "design successor queue staging",
        REQUIRED_CANONICAL_QUEUE_LISTS,
    )
    _verify_marker_block(
        errors,
        _configured_path("CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH", DEFAULT_SUCCESSOR_REGISTRY_PATH),
        "id: 102.1",
        REQUIRED_CANONICAL_REGISTRY_MARKERS,
        "successor registry",
    )

    if errors:
        print("desktop native trust receipt verification failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("desktop native trust receipts verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
