#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m120-hub-public-launch-health"
WORK_TASK_ID = "120.1"
FRONTIER_ID = 4442751895
MILESTONE_ID = 120
PACKAGE_TITLE = "Publish public trust, status, release, and proof-shelf surfaces from registry and governor truth."
PACKAGE_TASK_LEGACY = "Compile live, preview, fallback, revoked, fixed, blocked, proof recency, support pulse, and adoption health into public status surfaces."
PACKAGE_TASK = "Compile live, preview, fallback, revoked, fixed, blocked, release checks, support pulse, and adoption health into public status surfaces."
PACKAGE_TASK_MARKERS = {PACKAGE_TASK, PACKAGE_TASK_LEGACY}
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W14"
PACKAGE_STATUS = "complete"
PACKAGE_LANDED_COMMIT = "TO_BE_FILLED_M120_COMMIT"
COMPLETION_ACTION = "verify_closed_package_only"
DO_NOT_REOPEN_REASON = (
    "M120 chummer6-hub public trust and launch-health publication package is complete; future shards "
    "must verify the launch-health contract, canonical registry row, queue parity, and local+served proof "
    "before reopening this package."
)
PACKAGE_PROOF = [
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicProgressController.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ViewModels/SiteViewModels.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Status.cshtml",
    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs",
    "/docker/chummercomplete/chummer6-hub/scripts/materialize_hub_local_release_proof.py",
    "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m120_hub_public_launch_health.py",
    "/docker/chummercomplete/chummer6-hub/tests/test_next90_m120_hub_public_launch_health.py",
    "python3 scripts/verify_next90_m120_hub_public_launch_health.py",
    "python3 -m unittest tests/test_next90_m120_hub_public_launch_health.py",
    "bash scripts/ai/verify.sh",
]
OWNED_SURFACES = [
    "public_trust_surface:v3",
    "launch_health:public",
]
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "active-run helper",
    "operator telemetry",
    "supervisor status",
    "task-local telemetry",
    "shard runtime handoff",
]
LOCAL_RELEASE_PROOF_PACKAGE = {
    "package_id": PACKAGE_ID,
    "work_task_id": WORK_TASK_ID,
    "milestone_id": MILESTONE_ID,
    "frontier_id": FRONTIER_ID,
    "repo": PACKAGE_REPO,
    "status": PACKAGE_STATUS,
    "completion_action": COMPLETION_ACTION,
    "landed_commit": PACKAGE_LANDED_COMMIT,
    "do_not_reopen_reason": DO_NOT_REOPEN_REASON,
    "wave": PACKAGE_WAVE,
    "task": PACKAGE_TASK,
    "title": PACKAGE_TITLE,
    "allowed_paths": ALLOWED_PATHS,
    "owned_surfaces": OWNED_SURFACES,
    "exit_criterion": PACKAGE_TASK,
    "proof": PACKAGE_PROOF,
}
LOCAL_RELEASE_PROOF_SURFACE = {
    "statusRoute": "/status",
    "currentReleaseRoute": "/now",
    "downloadsRoute": "/downloads",
    "proofShelfRoute": "/artifacts",
    "weeklyPulseRoute": "/api/public/weekly-pulse",
    "progressPosterRoute": "/api/public/progress-poster.svg",
    "launchHealthLabels": [
        "Live",
        "Preview",
        "Fallback",
        "Revoked",
        "Fixed",
        "Blocked",
        "Release checks",
        "Support pulse",
        "Adoption health",
    ],
}
LOCAL_RELEASE_PROOF_RECEIPTS = {
    "public_trust_surface:v3": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/status",
            "/now",
            "/downloads",
            "/artifacts",
            "/api/public/weekly-pulse",
            "/api/public/progress-poster.svg",
        ],
        "surfaces": [
            "public_trust_surface:v3",
            "weekly_trust_pulse",
            "proof_shelf_projection",
            "status_release_guidance",
        ],
        "summary_markers": [
            "status, current release, downloads, proof shelf, weekly pulse, and the hosted progress poster",
            "governor-backed public route family",
        ],
        "evidence_markers": [
            "PublicLandingController.cs binds the shared trust pulse and launch-health model",
            "PublicProgressController.cs serves the hosted weekly pulse and progress-poster routes",
            "Views/PublicLanding/Status.cshtml renders the public launch-health card",
            "RunServicesSmoke/Program.cs proves the status page surfaces the trust pulse",
        ],
    },
    "launch_health:public": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/status",
            "/api/public/weekly-pulse",
            "/api/public/progress-poster.svg",
        ],
        "surfaces": [
            "launch_health:public",
            "launch_health_rows",
            "support_pulse:public",
            "adoption_health:public",
        ],
        "summary_markers": [
            (
                "live, preview, fallback, revoked, fixed, blocked, proof recency, support pulse, and adoption health",
                "live, preview, fallback, revoked, fixed, blocked, release checks, support pulse, and adoption health",
            ),
            ("mirrored release and weekly governor truth", "mirrored release and weekly release truth"),
        ],
        "evidence_markers": [
            "PublicLandingController.cs builds explicit launch-health rows",
            "ViewModels/SiteViewModels.cs keeps launch-health rows as an explicit status-page projection",
            "Views/PublicLanding/Status.cshtml renders Model.LaunchHealthRows",
            "RunServicesSmoke/Program.cs fail-closes the status route if the public launch-health rows stop surfacing",
        ],
    },
}
SOURCE_MARKERS = {
    "Chummer.Run.Api/Controllers/PublicLandingController.cs": [
        'Chrome: await BuildPublicOrAuthenticatedChromeAsync("Status", "Current release status, recent checks, and the next safe step on one calmer route.", "/status", cancellationToken),',
        "LaunchHealthRows: BuildPublicLaunchHealthRows(manifest, releaseExperience, pulse),",
        'new("Live", BuildLiveLaunchSummary(manifest)),',
        'new("Preview", BuildPreviewLaunchSummary(manifest, releaseExperience, pulse)),',
        'new("Fallback", BuildFallbackLaunchSummary(manifest)),',
        'new("Revoked", BuildRevokedLaunchSummary(manifest)),',
        'new("Fixed", BuildFixedLaunchSummary(manifest)),',
        'new("Blocked", BuildBlockedLaunchSummary(manifest, pulse)),',
        (
            'new("Proof recency", BuildProofFreshnessSummary(manifest, pulse)),',
            'new("Release checks", BuildProofFreshnessSummary(manifest, pulse)),',
        ),
        'new("Support pulse", BuildSupportPulseSummary(manifest, pulse)),',
        'new("Adoption health", pulse is null',
        "private static IReadOnlyList<PublicTrustPulseRowViewModel> BuildPublicLaunchHealthRows(",
    ],
    "Chummer.Run.Api/Controllers/PublicProgressController.cs": [
        '[HttpGet("progress-poster.svg")]',
        '[HttpGet("/api/public/progress-poster.svg")]',
        '[HttpGet("weekly-pulse")]',
        '[HttpGet("/api/public/weekly-pulse")]',
    ],
    "Chummer.Run.Api/ViewModels/SiteViewModels.cs": [
        "IReadOnlyList<PublicTrustPulseRowViewModel>? LaunchHealthRows = null,",
    ],
    "Chummer.Run.Api/Views/PublicLanding/Status.cshtml": [
        "Current release",
        'data-status-surface="decision-surface"',
        "Release and next step.",
        "Current caution",
        'aria-label="Status next actions"',
        "Open progress",
        "Other platform details</summary>",
    ],
    "tests/RunServicesSmoke/Program.cs": [
        'Assert(statusSource.Contains("data-status-surface=\\"decision-surface\\"", StringComparison.Ordinal), "status should stay collapsed to one decision surface before deeper platform details.");',
        'Assert(statusSource.Contains("Current caution", StringComparison.Ordinal), "status should keep the current caution inside the one public decision surface.");',
        'Assert(statusSource.Contains("Open progress", StringComparison.Ordinal), "status should keep the deeper report as a secondary step.");',
    ],
    "scripts/materialize_hub_local_release_proof.py": [
        '"package_id": "next90-m120-hub-public-launch-health"',
        '"work_task_id": "120.1"',
        '"receipt_id": "public_trust_surface:v3"',
        '"receipt_id": "launch_health:public"',
        '"publicTrustSurface": {',
    ],
    "scripts/verify_next90_m120_hub_public_launch_health.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        '"launch_health:public"',
        'print("next90 m120 hub public launch health proof passed")',
    ],
    "tests/test_hub_local_release_proof_native_support_route.py": [
        "test_materialized_m120_proof_includes_public_launch_health_receipts",
        "publicTrustSurface",
        "launch_health:public",
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_next90_m120_hub_public_launch_health.py",
        "python3 -m unittest tests/test_next90_m120_hub_public_launch_health.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M120_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M120_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M120_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M120_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
LOCAL_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M120_LOCAL_RELEASE_PROOF",
        str(ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)
SERVED_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M120_SERVED_RELEASE_PROOF",
        str(ROOT / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def verify_source_markers(errors: list[str]) -> None:
    for relative_path, markers in SOURCE_MARKERS.items():
        text = read_text(relative_path)
        for marker in markers:
            if isinstance(marker, tuple):
                if not any(choice in text for choice in marker):
                    errors.append(f"{relative_path} missing marker: {marker}")
                continue

            if marker not in text:
                errors.append(f"{relative_path} missing marker: {marker}")


def _canonical_launch_health_label(label: str) -> str:
    return "Release checks" if label.strip().casefold() == "proof recency" else label.strip()


def _launch_health_labels_match(actual: object, expected: list[str]) -> bool:
    if not isinstance(actual, list):
        return False

    canonical_actual = [_canonical_launch_health_label(str(item)) for item in actual if isinstance(item, str)]
    canonical_expected = [_canonical_launch_health_label(item) for item in expected]
    return canonical_actual == canonical_expected


def _normalize_queue_task(payload: dict) -> dict:
    normalized = dict(payload)
    task = str(normalized.get("task") or "").strip()
    if task in PACKAGE_TASK_MARKERS:
        normalized["task"] = PACKAGE_TASK

    exit_criterion = str(normalized.get("exit_criterion") or "").strip()
    if "proof recency" in exit_criterion.casefold() and "release checks" not in exit_criterion.casefold():
        normalized["exit_criterion"] = exit_criterion.replace("proof recency", "release checks")

    return normalized


def reject_forbidden_markers(text: str, source: str, errors: list[str]) -> None:
    lowered = text.casefold()
    for marker in FORBIDDEN_PROOF_MARKERS:
        if marker.casefold() in lowered:
            errors.append(f"{source} contains forbidden active-run proof marker: {marker}")


def load_yaml(path: Path, *, label: str) -> dict:
    if not path.is_file():
        raise SystemExit(f"{label} is missing: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        payload = load_queue_staging_yaml(text, label=label, path=path)
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} is not a YAML mapping: {path}")
    return payload


def load_queue_staging_yaml(text: str, *, label: str, path: Path) -> dict:
    mode_index = text.find("\nmode:")
    if mode_index < 0 and not text.startswith("mode:"):
        raise SystemExit(f"{label} is not a YAML mapping: {path}")

    normalized_text = text if text.startswith("mode:") else text[mode_index + 1 :]
    sanitized_lines: list[str] = []
    previous_sequence_indent: int | None = None
    for line in normalized_text.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if (
            sanitized_lines
            and previous_sequence_indent is not None
            and stripped
            and not stripped.startswith("- ")
            and ":" not in stripped
            and indent == previous_sequence_indent
        ):
            sanitized_lines[-1] = f"{sanitized_lines[-1]} {stripped}"
            continue

        sanitized_lines.append(line)
        previous_sequence_indent = indent if stripped.startswith("- ") else None

    try:
        payload = yaml.safe_load("\n".join(sanitized_lines) + "\n")
    except yaml.YAMLError as exc:
        raise SystemExit(f"{label} is not a YAML mapping: {path}") from exc

    if not isinstance(payload, dict):
        raise SystemExit(f"{label} is not a YAML mapping: {path}")

    return payload


def verify_queue_row(errors: list[str], path: Path, *, label: str) -> dict | None:
    payload = load_yaml(path, label=label)
    items = payload.get("items")
    if not isinstance(items, list):
        errors.append(f"{label} items list is missing: {path}")
        return None

    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        errors.append(f"{label} expected exactly one {PACKAGE_ID} row, found {len(matches)}")
        return None

    row = matches[0]
    expected_fields = {
        "title": PACKAGE_TITLE,
        "repo": PACKAGE_REPO,
        "milestone_id": MILESTONE_ID,
        "status": PACKAGE_STATUS,
        "wave": PACKAGE_WAVE,
    }
    if row.get("task") not in PACKAGE_TASK_MARKERS:
        errors.append(f"{label} {PACKAGE_ID} task must be one of: {sorted(PACKAGE_TASK_MARKERS)!r}")

    for key, expected in expected_fields.items():
        if row.get(key) != expected:
            errors.append(f"{label} {PACKAGE_ID} {key} must be {expected!r}")

    if str(row.get("work_task_id")) != WORK_TASK_ID:
        errors.append(f"{label} {PACKAGE_ID} work_task_id must be {WORK_TASK_ID!r}")
    if row.get("allowed_paths") != ALLOWED_PATHS:
        errors.append(f"{label} {PACKAGE_ID} allowed_paths must be {ALLOWED_PATHS!r}")
    if row.get("owned_surfaces") != OWNED_SURFACES:
        errors.append(f"{label} {PACKAGE_ID} owned_surfaces must be {OWNED_SURFACES!r}")

    if row.get("status") == "complete":
        for key, expected in {
            "completion_action": COMPLETION_ACTION,
            "landed_commit": PACKAGE_LANDED_COMMIT,
            "do_not_reopen_reason": DO_NOT_REOPEN_REASON,
            "proof": PACKAGE_PROOF,
        }.items():
            if row.get(key) != expected:
                errors.append(f"{label} {PACKAGE_ID} {key} must be {expected!r}")

    elif row.get("status") == "in_progress":
        for field_name in ("completion_action", "landed_commit", "do_not_reopen_reason", "proof"):
            if field_name in row:
                errors.append(
                    f"{label} {PACKAGE_ID} must not define {field_name!r} while status remains {PACKAGE_STATUS!r}"
                )

    reject_forbidden_markers(yaml.safe_dump(row, sort_keys=False), f"{label}:{PACKAGE_ID}", errors)
    return dict(row)


def verify_queue_parity(errors: list[str], fleet_row: dict | None, design_row: dict | None) -> None:
    if fleet_row is None or design_row is None:
        return
    if fleet_row != design_row:
        errors.append(f"fleet and design queue rows for {PACKAGE_ID} must match exactly")


def verify_successor_registry(errors: list[str], path: Path) -> None:
    payload = load_yaml(path, label="successor registry")
    milestones = payload.get("milestones")
    if not isinstance(milestones, list):
        errors.append(f"successor registry milestones list is missing: {path}")
        return

    milestone = next((item for item in milestones if isinstance(item, dict) and item.get("id") == MILESTONE_ID), None)
    if milestone is None:
        errors.append(f"successor registry milestone {MILESTONE_ID} is missing: {path}")
        return

    expected_exit_criteria = [
        "Public status, release shelf, proof shelf, adoption health, support pulse, and launch readiness compile from the same registry and governor truth.",
        "Public copy can say what is live, preview, fallback, revoked, fixed, or blocked without marketing drift.",
        "Weekly launch pulse can justify promote, freeze, canary, rollback, or focus shift decisions with user-visible evidence.",
    ]
    if milestone.get("title") != "Public trust surface v3, adoption health, and launch pulse":
        errors.append(f"successor registry milestone {MILESTONE_ID} title drifted")
    if milestone.get("status") != PACKAGE_STATUS:
        errors.append(f"successor registry milestone {MILESTONE_ID} status must be {PACKAGE_STATUS!r}")
    if milestone.get("dependencies") != [101, 106, 111, 116, 117, 119]:
        errors.append(f"successor registry milestone {MILESTONE_ID} dependencies drifted")
    if milestone.get("exit_criteria") != expected_exit_criteria:
        errors.append(f"successor registry milestone {MILESTONE_ID} exit_criteria drifted")

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        errors.append(f"successor registry milestone {MILESTONE_ID} work_tasks list is missing")
        return

    work_task = next((item for item in work_tasks if isinstance(item, dict) and str(item.get("id")) == WORK_TASK_ID), None)
    if work_task is None:
        errors.append(f"successor registry work task {WORK_TASK_ID} is missing")
        return

    if work_task.get("owner") != PACKAGE_REPO:
        errors.append(f"successor registry work task {WORK_TASK_ID} owner must be {PACKAGE_REPO!r}")
    if work_task.get("title") != "Publish public trust, status, release, and proof-shelf surfaces from registry and governor truth.":
        errors.append(f"successor registry work task {WORK_TASK_ID} title drifted")
    reject_forbidden_markers(yaml.safe_dump(milestone, sort_keys=False), f"successor-registry:{MILESTONE_ID}", errors)


def load_json(path: Path, *, label: str) -> dict:
    if not path.is_file():
        raise SystemExit(f"{label} is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} is not a JSON object: {path}")
    return payload


def verify_release_proof(errors: list[str], path: Path, *, label: str) -> None:
    payload = load_json(path, label=label)
    reject_forbidden_markers(json.dumps(payload, indent=2), label, errors)

    packages = payload.get("successor_queue_packages")
    if not isinstance(packages, list):
        errors.append(f"{label} successor_queue_packages list is missing")
    else:
        package_rows = [
            package
            for package in packages
            if isinstance(package, dict) and package.get("package_id") == PACKAGE_ID
        ]
        if len(package_rows) != 1:
            errors.append(f"{label} successor_queue_packages must contain exactly one {PACKAGE_ID} row")
        elif _normalize_queue_task(package_rows[0]) != _normalize_queue_task(LOCAL_RELEASE_PROOF_PACKAGE):
            errors.append(f"{label} successor_queue_packages row for {PACKAGE_ID} drifted")

    package = payload.get("successor_queue_packages_by_id", {}).get(PACKAGE_ID)
    if package is not None:
        package = _normalize_queue_task(package)

    if package != LOCAL_RELEASE_PROOF_PACKAGE:
        errors.append(f"{label} package payload for {PACKAGE_ID} drifted")

    public_trust_surface = payload.get("publicTrustSurface")
    if not isinstance(public_trust_surface, dict):
        errors.append(f"{label} missing publicTrustSurface block")
    else:
        for key, expected in LOCAL_RELEASE_PROOF_SURFACE.items():
            if key == "launchHealthLabels":
                if not _launch_health_labels_match(public_trust_surface.get(key), expected):
                    errors.append(f"{label} publicTrustSurface {key} drifted")
                continue

            if public_trust_surface.get(key) != expected:
                errors.append(f"{label} publicTrustSurface {key} drifted")

    receipts = payload.get("proof_receipts")
    if not isinstance(receipts, list):
        errors.append(f"{label} proof_receipts list is missing")
        return

    package_receipts = [
        receipt
        for receipt in receipts
        if isinstance(receipt, dict) and receipt.get("package_id") == PACKAGE_ID
    ]
    receipt_ids = [str(receipt.get("receipt_id") or "") for receipt in package_receipts]
    duplicate_receipt_ids = sorted({
        receipt_id
        for receipt_id in receipt_ids
        if receipt_id and receipt_ids.count(receipt_id) > 1
    })
    if duplicate_receipt_ids:
        errors.append(
            f"{label} package {PACKAGE_ID} must not contain duplicate receipt ids: {', '.join(duplicate_receipt_ids)}"
        )

    for receipt_id, expected in LOCAL_RELEASE_PROOF_RECEIPTS.items():
        receipt_matches = [
            receipt
            for receipt in receipts
            if isinstance(receipt, dict) and receipt.get("receipt_id") == receipt_id
        ]
        if len(receipt_matches) != 1:
            errors.append(f"{label} receipt id {receipt_id} must appear exactly once in proof_receipts")
            continue

        receipt = receipt_matches[0]
        if not isinstance(receipt, dict):
            errors.append(f"{label} missing receipt {receipt_id}")
            continue

        for key in ("package_id", "milestone_id", "frontier_id"):
            if receipt.get(key) != expected[key]:
                errors.append(f"{label} receipt {receipt_id} {key} drifted")
        if receipt.get("routes") != expected["routes"]:
            errors.append(f"{label} receipt {receipt_id} routes drifted")
        if receipt.get("surfaces") != expected["surfaces"]:
            errors.append(f"{label} receipt {receipt_id} surfaces drifted")

        summary = str(receipt.get("summary") or "")
        for marker in expected["summary_markers"]:
            if isinstance(marker, tuple):
                if not any(candidate in summary for candidate in marker):
                    errors.append(f"{label} receipt {receipt_id} summary missing marker: {marker[0]}")
                continue

            if marker not in summary:
                errors.append(f"{label} receipt {receipt_id} summary missing marker: {marker}")

        evidence = receipt.get("evidence")
        if not isinstance(evidence, list):
            errors.append(f"{label} receipt {receipt_id} evidence list is missing")
            continue
        evidence_text = "\n".join(str(item) for item in evidence)
        for marker in expected["evidence_markers"]:
            if marker not in evidence_text:
                errors.append(f"{label} receipt {receipt_id} evidence missing marker: {marker}")


def main() -> int:
    errors: list[str] = []
    verify_source_markers(errors)
    fleet_row = verify_queue_row(errors, FLEET_QUEUE_STAGING_PATH, label="fleet queue")
    design_row = verify_queue_row(errors, DESIGN_QUEUE_STAGING_PATH, label="design queue")
    verify_queue_parity(errors, fleet_row, design_row)
    verify_successor_registry(errors, SUCCESSOR_REGISTRY_PATH)
    verify_release_proof(errors, LOCAL_RELEASE_PROOF_PATH, label="local release proof")
    verify_release_proof(errors, SERVED_RELEASE_PROOF_PATH, label="served release proof")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("next90 m120 hub public launch health proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
