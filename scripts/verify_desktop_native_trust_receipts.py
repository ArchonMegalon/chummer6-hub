#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


PACKAGE_ID = "next90-m102-hub-desktop-native-trust"
LANDED_COMMIT = "160af58f"
FRONTIER_ID = 2897065929

REQUIRED_SOURCE_MARKERS = {
    Path("Chummer.Run.Api/Controllers/InstallLinkingController.cs"): [
        '[HttpPost("continuation")]',
        "ResolveInstallationForGrant(request.InstallationId, request.AccessToken)",
        "DesktopInstallRail.BuildContinuationReceipt(releaseArtifact, manifest, recoveryMode: false)",
        "FallbackPosture: continuation?.FallbackPosture",
        "BuildNativeNextSafeAction(updateAvailable, leadSupportCase, continuation)",
        "ResolveSupportContinuationCases(installation, installSummary, receipt)",
        "InstalledBuildReceiptId: receipt?.ReceiptId",
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
    Path("Chummer.Run.Api/Views/Accounts/Account.cshtml"): [
        "The next safe action is still inside Chummer on the already-downloaded device.",
        "Only use the recovery code if that copy explicitly enters recovery mode.",
        "Claim, update, rollback, recovery, and support stay on this same account rail once the install is linked.",
        "Use Devices & access for relinking, guided update follow-through, and support closure on the same copy.",
        "instead of starting a fresh browser ritual.",
    ],
    Path("tests/RunServicesVerification/InstallLinkingContinuationVerification.cs"): [
        "ContinueClaimedInstall(",
        "response.FallbackPosture.Contains(\"Claim codes are a recovery fallback\"",
        "UpdateAvailable",
        "NeedsInstallUpdate",
        "response.SupportCases[0].InstalledBuildReceiptId",
        "Support follow-through should expose installed build version truth.",
        "Invalid desktop continuation grants should fail closed.",
    ],
    Path("scripts/ai/verify.sh"): [
        "python3 scripts/verify_desktop_native_trust_receipts.py",
    ],
}


REQUIRED_PROOF_RECEIPTS = {
    "desktop_native_claim_and_recovery": {
        "package_id": "next90-m102-hub-desktop-native-trust",
        "milestone_id": 102,
        "frontier_id": FRONTIER_ID,
        "summary": (
            "Claim and recovery continuation now have installer/app-native receipts: guided setup is the default, "
            "claim codes are recovery fallback only, and the claimed desktop app can call the grant-bound "
            "continuation endpoint without a browser redemption ritual."
        ),
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
        "summary": (
            "Support follow-through carries installed build, current release, channel, head, platform, fallback, "
            "update, and rollback truth on the same install rail used by the desktop client."
        ),
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

REQUIRED_TOP_LEVEL_PROOF_ROUTES = [
    "/downloads/install/avalonia-linux-x64-installer/continue.json",
    "/api/v1/install-linking/continuation",
    "/account/access",
    "/account/support",
    "/contact",
]

REQUIRED_TOP_LEVEL_JOURNEYS = [
    "install_claim_restore_continue",
]


REQUIRED_CANONICAL_QUEUE_MARKERS = [
    "title: Unify claim, install, update, and support recovery into one desktop-native flow",
    "task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
    f"package_id: {PACKAGE_ID}",
    f"frontier_id: {FRONTIER_ID}",
    "milestone_id: 102",
    "wave: W6",
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

REQUIRED_CANONICAL_REGISTRY_LISTS = {
    "evidence": [
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InstallLinkingController.cs exposes /api/v1/install-linking/continuation for grant-bound claimed desktop installs with current release, update, rollback, and support continuation truth.",
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml and /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/Accounts/Account.cshtml make guided setup/app continuation the default and keep claim codes as recovery fallback only.",
        "/docker/chummercomplete/chummer.run-services/scripts/verify_desktop_native_trust_receipts.py fail-closes missing source markers and missing successor proof receipts for desktop_native_claim_and_recovery and support_followthrough:install_truth.",
        "/docker/chummercomplete/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json carries next90-m102-hub-desktop-native-trust proof receipts for /downloads/install/avalonia-linux-x64-installer/continue.json, /api/v1/install-linking/continuation, /account/access, /account/support, and /contact.",
        "/docker/chummercomplete/chummer.run-services commit e27f24c1 tightens desktop-native continuation fallback-posture proof so claimed installs return the same fallback posture used by download and support recovery.",
        "/docker/chummercomplete/chummer.run-services commit e578a519 tightens the completed M102 proof pin so future shards verify the closed package instead of repeating it.",
        "/docker/chummercomplete/chummer.run-services commit 9fcec2a0 fail-closes M102 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
        "/docker/chummercomplete/chummer.run-services commit 266d526b pins the M102 queue proof hardening commit so stale queue proof cannot keep the package green.",
        "/docker/chummercomplete/chummer.run-services commit 6ea510c8 pins the M102 telemetry guard proof evidence so future shards verify the latest closed-package guard.",
        "/docker/chummercomplete/chummer.run-services commit 7a825c73 pins the M102 desktop trust guard evidence into the verifier and unit guard.",
        "/docker/chummercomplete/chummer.run-services commit aff39474 pins the M102 desktop trust latest guard.",
        "/docker/chummercomplete/chummer.run-services commit 38d50742 pins the M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit b9404a4c pins the M102 desktop trust latest proof guard.",
        "/docker/chummercomplete/chummer.run-services commit e6ae11a7 pins the M102 desktop trust guard closure.",
        "/docker/chummercomplete/chummer.run-services commit 4c542b50 pins the latest M102 desktop trust closure guard.",
        "/docker/chummercomplete/chummer.run-services commit 02bed909 pins the M102 desktop trust closure guard.",
        "/docker/chummercomplete/chummer.run-services commit 2017cdfe requires the latest M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 24432002 tightens the current M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 4afd6c3e pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit d99d080e pins the M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit b5b25e98 tightens M102 desktop trust proof floor.",
        "python3 scripts/verify_desktop_native_trust_receipts.py and python3 -m unittest tests/test_desktop_native_trust_receipts.py exit 0.",
        'dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "DesktopInstallRailTests|PublicLandingClaimRecoveryFlowTests|InstallLinkingContinuationVerification" --no-restore exits 0 for net10.0 and net10.0-windows.',
    ],
}

REQUIRED_CANONICAL_QUEUE_LISTS = {
    "proof": [
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InstallLinkingController.cs",
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/DesktopInstallRail.cs",
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/Support/SupportCasePresentationService.cs",
        "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml",
        "/docker/chummercomplete/chummer.run-services/scripts/verify_desktop_native_trust_receipts.py",
        "/docker/chummercomplete/chummer.run-services/tests/test_desktop_native_trust_receipts.py",
        "/docker/chummercomplete/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
        "/docker/chummercomplete/chummer.run-services commit e27f24c1 tightens desktop-native continuation fallback-posture proof.",
        "/docker/chummercomplete/chummer.run-services commit e578a519 tightens the completed M102 proof pin.",
        "/docker/chummercomplete/chummer.run-services commit 9fcec2a0 fail-closes M102 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
        "/docker/chummercomplete/chummer.run-services commit 266d526b pins the M102 queue proof hardening commit.",
        "/docker/chummercomplete/chummer.run-services commit 6ea510c8 pins the M102 telemetry guard proof evidence.",
        "/docker/chummercomplete/chummer.run-services commit 7a825c73 pins the M102 desktop trust guard evidence.",
        "/docker/chummercomplete/chummer.run-services commit aff39474 pins the M102 desktop trust latest guard.",
        "/docker/chummercomplete/chummer.run-services commit 38d50742 pins the M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit b9404a4c pins the M102 desktop trust latest proof guard.",
        "/docker/chummercomplete/chummer.run-services commit e6ae11a7 pins the M102 desktop trust guard closure.",
        "/docker/chummercomplete/chummer.run-services commit 4c542b50 pins the latest M102 desktop trust closure guard.",
        "/docker/chummercomplete/chummer.run-services commit 02bed909 pins the M102 desktop trust closure guard.",
        "/docker/chummercomplete/chummer.run-services commit 2017cdfe requires the latest M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 24432002 tightens the current M102 desktop trust proof guard.",
        "/docker/chummercomplete/chummer.run-services commit 4afd6c3e pins the current M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit d99d080e pins the M102 desktop trust proof floor.",
        "/docker/chummercomplete/chummer.run-services commit b5b25e98 tightens M102 desktop trust proof floor.",
        "python3 scripts/verify_desktop_native_trust_receipts.py",
        "python3 -m unittest tests/test_desktop_native_trust_receipts.py",
        'dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "DesktopInstallRailTests|PublicLandingClaimRecoveryFlowTests|InstallLinkingContinuationVerification" --no-restore',
    ],
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

FORBIDDEN_PROOF_MARKERS = [
    "/var/lib/codex-fleet",
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "active-run helper",
    "operator telemetry",
    "design_supervisor_ooda",
]

REQUIRED_PROOF_PACKAGE = {
    "package_id": PACKAGE_ID,
    "milestone_id": 102,
    "frontier_id": FRONTIER_ID,
    "status": "complete",
    "landed_commit": LANDED_COMMIT,
    "title": "Unify claim, install, update, and support recovery into one desktop-native flow",
    "allowed_paths": REQUIRED_CANONICAL_QUEUE_LISTS["allowed_paths"],
    "owned_surfaces": REQUIRED_CANONICAL_QUEUE_LISTS["owned_surfaces"],
    "exit_criterion": "Claim, update, rollback, recovery, and support followthrough happen from the installer or app, not as browser ritual.",
}

REQUIRED_RESOLVING_COMMITS = [
    LANDED_COMMIT,
    "e27f24c1",
    "0ea22419",
    "b4d761a2",
    "e75c4a97",
    "e578a519",
    "9fcec2a0",
    "266d526b",
    "6ea510c8",
    "7a825c73",
    "aff39474",
    "38d50742",
    "b9404a4c",
    "e6ae11a7",
    "4c542b50",
    "02bed909",
    "2017cdfe",
    "24432002",
    "4afd6c3e",
    "d99d080e",
    "b5b25e98",
]

DEFAULT_PROOF_PATH = Path(".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json")
DEFAULT_QUEUE_STAGING_PATH = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
DEFAULT_DESIGN_QUEUE_STAGING_PATH = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
DEFAULT_SUCCESSOR_REGISTRY_PATH = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml")
ABSOLUTE_REPO_PREFIX = "/docker/chummercomplete/chummer.run-services/"
MATERIALIZER_ARGS = [
    "https://chummer.run",
    "docker-compose.yml",
    "120",
    "true",
]


def _configured_path(env_name: str, default_path: Path) -> Path:
    override = os.environ.get(env_name)
    return Path(override) if override else default_path


def _configured_repo_anchor_root(repo_root: Path) -> Path:
    override = os.environ.get("CHUMMER_RUN_SERVICES_PROOF_ANCHOR_ROOT")
    return Path(override) if override else repo_root


def _proof_path(repo_root: Path) -> Path:
    configured = _configured_path("CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH", DEFAULT_PROOF_PATH)
    return configured if configured.is_absolute() else repo_root / configured


def _extract_yaml_block(text: str, anchor: str) -> str | None:
    anchor_index = text.find(anchor)
    if anchor_index < 0:
        return None

    item_start = text.rfind("\n  - ", 0, anchor_index)
    start = anchor_index if item_start < 0 else item_start + 1
    next_item = text.find("\n  - ", start + 1)
    return text[start:] if next_item < 0 else text[start:next_item]


def _verify_marker_block(
    errors: list[str],
    path: Path,
    anchor: str,
    markers: list[str],
    label: str,
    required_lists: dict[str, list[str]] | None = None,
    forbidden_markers: list[str] | None = None,
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

    if forbidden_markers is not None:
        for marker in forbidden_markers:
            if marker in block:
                errors.append(f"canonical {label} block has forbidden active-run proof marker: {marker}")

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


def _repo_anchor_from_proof_text(value: str) -> Path | None:
    if not value.startswith(ABSOLUTE_REPO_PREFIX):
        return None

    relative = value[len(ABSOLUTE_REPO_PREFIX) :].split(" ", 1)[0].strip()
    return Path(relative) if relative else None


def _required_repo_anchor_paths() -> list[Path]:
    anchors: list[Path] = []
    for values in (
        REQUIRED_CANONICAL_QUEUE_LISTS["proof"],
        REQUIRED_CANONICAL_REGISTRY_LISTS["evidence"],
    ):
        for value in values:
            anchor = _repo_anchor_from_proof_text(value)
            if anchor is not None and anchor not in anchors:
                anchors.append(anchor)

    return anchors


def _verify_required_repo_anchor_paths(errors: list[str], repo_root: Path) -> None:
    anchor_root = _configured_repo_anchor_root(repo_root)
    for relative_path in _required_repo_anchor_paths():
        if not (anchor_root / relative_path).exists():
            errors.append(f"canonical proof anchor does not resolve: {ABSOLUTE_REPO_PREFIX}{relative_path}")


def _required_resolving_commits() -> list[str]:
    commits = list(REQUIRED_RESOLVING_COMMITS)
    extra_commits = os.environ.get("CHUMMER_DESKTOP_NATIVE_TRUST_EXTRA_REQUIRED_COMMITS", "")
    for commit in extra_commits.split(","):
        commit = commit.strip()
        if commit and commit not in commits:
            commits.append(commit)

    return commits


def _verify_required_commits(errors: list[str], repo_root: Path) -> None:
    for commit in _required_resolving_commits():
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append(f"required M102 desktop-native trust proof commit does not resolve: {commit}")


def _verify_required_source_markers(errors: list[str], repo_root: Path) -> None:
    for relative_path, markers in REQUIRED_SOURCE_MARKERS.items():
        path = repo_root / relative_path
        if not path.is_file():
            errors.append(f"missing source file: {relative_path}")
            continue

        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                errors.append(f"{relative_path} missing marker: {marker}")


def _stable_json_payload(path: Path, errors: list[str], label: str) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{label} is not valid json: {exc}")
        return None

    if not isinstance(payload, dict):
        errors.append(f"{label} is not a json object")
        return None

    stable = dict(payload)
    stable.pop("generated_at", None)
    return stable


def _verify_materialized_proof_reproducible(errors: list[str], repo_root: Path, proof_path: Path) -> None:
    materializer_path = repo_root / "scripts" / "materialize_hub_local_release_proof.py"
    if not materializer_path.is_file():
        errors.append("missing proof materializer: scripts/materialize_hub_local_release_proof.py")
        return

    published = _stable_json_payload(proof_path, errors, "published proof file")
    if published is None:
        return

    with tempfile.TemporaryDirectory() as temp_root:
        expected_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
        result = subprocess.run(
            ["python3", str(materializer_path), str(expected_path), *MATERIALIZER_ARGS],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append(
                "proof materializer failed while checking reproducibility: "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            )
            return

        expected = _stable_json_payload(expected_path, errors, "materialized proof file")
        if expected is None:
            return

    if published != expected:
        errors.append(
            "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from "
            "scripts/materialize_hub_local_release_proof.py for next90-m102-hub-desktop-native-trust"
        )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    errors: list[str] = []

    _verify_required_repo_anchor_paths(errors, repo_root)
    _verify_required_commits(errors, repo_root)
    _verify_required_source_markers(errors, repo_root)

    proof_path = _proof_path(repo_root)
    if not proof_path.is_file():
        try:
            display_path = proof_path.relative_to(repo_root)
        except ValueError:
            display_path = proof_path
        errors.append(f"missing proof file: {display_path}")
    else:
        _verify_materialized_proof_reproducible(errors, repo_root, proof_path)
        try:
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"proof file is not valid json: {exc}")
        else:
            proof_routes = proof.get("proof_routes")
            if not isinstance(proof_routes, list):
                errors.append("proof missing list field: proof_routes")
            else:
                proof_route_set = {item for item in proof_routes if isinstance(item, str)}
                for required in REQUIRED_TOP_LEVEL_PROOF_ROUTES:
                    if required not in proof_route_set:
                        errors.append(f"proof_routes missing M102 route: {required}")

            journeys_passed = proof.get("journeys_passed")
            if not isinstance(journeys_passed, list):
                errors.append("proof missing list field: journeys_passed")
            else:
                journey_set = {item for item in journeys_passed if isinstance(item, str)}
                for required in REQUIRED_TOP_LEVEL_JOURNEYS:
                    if required not in journey_set:
                        errors.append(f"journeys_passed missing M102 journey: {required}")

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

                for key in ("package_id", "milestone_id", "frontier_id", "summary"):
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
        FORBIDDEN_PROOF_MARKERS,
    )
    _verify_marker_block(
        errors,
        _configured_path("CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH", DEFAULT_DESIGN_QUEUE_STAGING_PATH),
        f"package_id: {PACKAGE_ID}",
        REQUIRED_CANONICAL_QUEUE_MARKERS,
        "design successor queue staging",
        REQUIRED_CANONICAL_QUEUE_LISTS,
        FORBIDDEN_PROOF_MARKERS,
    )
    _verify_marker_block(
        errors,
        _configured_path("CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH", DEFAULT_SUCCESSOR_REGISTRY_PATH),
        "id: 102.1",
        REQUIRED_CANONICAL_REGISTRY_MARKERS,
        "successor registry",
        REQUIRED_CANONICAL_REGISTRY_LISTS,
        FORBIDDEN_PROOF_MARKERS,
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
