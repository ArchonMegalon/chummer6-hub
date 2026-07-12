#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m114-hub-rule-environment-receipts"
WORK_TASK_ID = "114.3"
FRONTIER_ID = 4934642390
MILESTONE_ID = 114
PACKAGE_TITLE = "Keep campaign, support, and install-aware diagnostics tied to the same rule-environment receipts"
PACKAGE_TASK = "Keep campaign, support, and install-aware diagnostics tied to the same rule-environment receipts."
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W12"
PACKAGE_STATUS = "complete"
PACKAGE_COMPLETION_ACTION = "verify_closed_package_only"
PACKAGE_DO_NOT_REOPEN_REASON = (
    "M114 chummer6-hub rule-environment receipts are complete; future shards must verify this package receipt, "
    "registry row, queue row, and design-queue row instead of reopening the campaign/support/install-aware receipt lane."
)
OWNED_SURFACES = {
    "campaign_rule_environment_receipts",
    "support_rule_environment_receipts",
    "install_aware_support_receipts",
}
ALLOWED_PATHS = {"Chummer.Run.Api", "scripts", "tests"}
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
    "wave": PACKAGE_WAVE,
    "task": PACKAGE_TASK,
    "title": PACKAGE_TITLE,
    "completion_action": PACKAGE_COMPLETION_ACTION,
    "do_not_reopen_reason": PACKAGE_DO_NOT_REOPEN_REASON,
    "allowed_paths": sorted(ALLOWED_PATHS),
    "owned_surfaces": sorted(OWNED_SURFACES),
    "exit_criterion": PACKAGE_TASK,
}
LOCAL_RELEASE_PROOF_RECEIPTS = {
    "campaign_rule_environment_receipts": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/home",
            "/account/roster",
            "/api/v1/campaign-spine/me",
            "/api/v1/campaign-spine/me/rules/{entryId}",
        ],
        "surfaces": [
            "campaign_rule_environment_receipts",
            "rules_navigator",
            "rule_environment_studio:hub",
        ],
        "summary_markers": [
            "campaign",
            "explain-entry receipts",
            "rule-environment studio",
        ],
        "evidence_markers": [
            "CampaignSpineService.cs projects rules navigator answers with stable ExplainEntryId values",
            "RunServicesSmoke/Program.cs proves signed-in account and home surfaces keep grounded rules navigator answers",
            "verify_next90_m114_hub_rule_environment_receipts.py fail-closes queue, registry, and proof drift",
        ],
    },
    "support_rule_environment_receipts": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/api/v1/support/cases/assistant",
            "/home",
            "/api/v1/campaign-spine/me/rules/{entryId}",
        ],
        "surfaces": [
            "support_rule_environment_receipts",
            "support_assistant",
            "rules_truth",
        ],
        "summary_markers": [
            "support assistant",
            "explain-entry receipts",
            "campaign-owned rules truth",
        ],
        "evidence_markers": [
            "SupportAssistantService.cs forwards RulesNavigator ExplainEntryId values into support citations",
            "SupportContracts.cs preserves optional citation receipt ids",
            "RunServicesSmoke/Program.cs proves rules-truth assistant answers expose the same explain receipt ids",
        ],
    },
    "install_aware_support_receipts": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/api/v1/support/cases/assistant",
            "/account/access",
            "/account/roster",
            "/home",
        ],
        "surfaces": [
            "install_aware_support_receipts",
            "support_assistant",
            "install_aware_diagnostics",
        ],
        "summary_markers": [
            "install-aware",
            "receipt-backed rule-environment lane",
            "grounded campaign or build explain receipt",
        ],
        "evidence_markers": [
            "SupportAssistantService.cs keeps installation-aware rules and build questions tied to open_home and open_work actions",
            "RunServicesSmoke/Program.cs proves install-aware rules and build assistant requests route back to the signed-in home and work surfaces",
            "verify_next90_m114_hub_rule_environment_receipts.py rejects release-proof drift when install-aware support receipts stop naming the shared rule-environment support lane",
        ],
    },
}
SOURCE_MARKERS = {
    "Chummer.Control.Contracts/SupportContracts.cs": [
        "public sealed record SupportAssistantCitation(",
        "string? ReceiptId = null);",
    ],
    "Chummer.Run.Api/Services/Support/SupportAssistantService.cs": [
        'SourceKind: "rules_truth",',
        'SourceKind: "build_truth",',
        'ReceiptId: entry.ExplainEntryId))',
        'Add("open_home", "Open home", "/home", "Review the current rule environment, campaign workspace, and grounded answer path.");',
        'Add("open_work", "Open work", "/account/roster", "Review the current build path, living dossier, and campaign return rail.");',
    ],
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs": [
        'ExplainEntryId: $"rules.navigator.{workspace.WorkspaceId}",',
        'ExplainEntryId: $"{explainRoot}:campaign-return"),',
        'ExplainEntryId: $"{explainRoot}:rule-environment")',
        "BuildRuleEnvironmentStudio(",
    ],
    "tests/RunServicesSmoke/Program.cs": [
        'string.Equals(item.SourceKind, "rules_truth", StringComparison.Ordinal)',
        'string.Equals(item.SourceKind, "build_truth", StringComparison.Ordinal)',
        "support assistant should reuse rules navigator truth for grounded campaign-rule questions.",
        "support assistant should route grounded rules questions back to the signed-in home cockpit.",
        "support assistant should route build-path questions back to the signed-in work surface.",
        "same explain receipt ids surfaced by campaign rules navigator entries",
    ],
    "scripts/materialize_hub_local_release_proof.py": [
        '"package_id": "next90-m114-hub-rule-environment-receipts"',
        '"work_task_id": "114.3"',
        '"receipt_id": "campaign_rule_environment_receipts"',
        '"receipt_id": "support_rule_environment_receipts"',
        '"receipt_id": "install_aware_support_receipts"',
    ],
    "scripts/verify_next90_m114_hub_rule_environment_receipts.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        "LOCAL_RELEASE_PROOF_RECEIPTS = {",
        "verify_queue_row(errors, FLEET_QUEUE_STAGING_PATH, label=\"fleet queue\")",
        "verify_queue_row(errors, DESIGN_QUEUE_STAGING_PATH, label=\"design queue\")",
        "verify_release_proof(errors, LOCAL_RELEASE_PROOF_PATH, label=\"repo-local release proof\")",
        "verify_release_proof(errors, SERVED_RELEASE_PROOF_PATH, label=\"served release proof\")",
        "rule-environment receipt proof passed",
    ],
    "tests/test_next90_m114_hub_rule_environment_receipts.py": [
        "verify_next90_m114_hub_rule_environment_receipts.py",
        "test_verifier_accepts_repo_local_m114_rule_environment_receipts",
        "test_verifier_fails_when_rules_truth_receipt_link_is_removed",
        "test_materialized_release_proof_includes_m114_rule_environment_receipts",
        "next90-m114-hub-rule-environment-receipts",
    ],
    "tests/test_hub_local_release_proof_native_support_route.py": [
        "test_materialized_m114_proof_includes_rule_environment_receipts",
        "campaign_rule_environment_receipts",
        "support_rule_environment_receipts",
        "install_aware_support_receipts",
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_next90_m114_hub_rule_environment_receipts.py",
        "python3 -m unittest tests/test_next90_m114_hub_rule_environment_receipts.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M114_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M114_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M114_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M114_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
LOCAL_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M114_LOCAL_RELEASE_PROOF",
        str(ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)
SERVED_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M114_SERVED_RELEASE_PROOF",
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
            if marker not in text:
                errors.append(f"{relative_path} missing marker: {marker}")


def reject_forbidden_markers(text: str, source: str, errors: list[str]) -> None:
    lowered = text.casefold()
    for marker in FORBIDDEN_PROOF_MARKERS:
        if marker.casefold() in lowered:
            errors.append(f"{source} contains forbidden active-run proof marker: {marker}")


def load_yaml(path: Path, *, label: str) -> dict:
    if not path.is_file():
        raise SystemExit(f"{label} is missing: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} must be a mapping: {path}")
    return payload


def normalize_legacy_queue_payload(raw: str) -> str:
    marker = raw.find("items:")
    if marker >= 0:
        raw = raw[marker:]

    def is_key_line(candidate: str) -> bool:
        text = candidate.lstrip()
        if not text or text.startswith(("-", "?")):
            return False
        if ":" not in text:
            return False
        key, _, _ = text.partition(":")
        return bool(key) and " " not in key and "\t" not in key

    normalized: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            normalized.append("")
            continue
        if (
            normalized
            and line.startswith(" ")
            and not line.lstrip().startswith("-")
            and not is_key_line(line)
            and not line.strip().startswith("?")
        ):
            normalized[-1] = f"{normalized[-1]} {line.strip()}"
        else:
            normalized.append(line)

    return "\n".join(normalized) + "\n"


def load_queue_payload(path: Path, *, label: str) -> dict:
    raw = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(raw)
        if isinstance(payload, dict):
            return payload
    except yaml.YAMLError:
        payload = yaml.safe_load(normalize_legacy_queue_payload(raw))
        if isinstance(payload, dict):
            return payload
    raise SystemExit(f"{label} must be a mapping: {path}")


def verify_queue_row(errors: list[str], path: Path, *, label: str) -> None:
    payload = load_queue_payload(path, label=label)
    items = payload.get("items")
    if not isinstance(items, list):
        errors.append(f"{label} items must be a list: {path}")
        return
    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        errors.append(f"{label} must contain exactly one {PACKAGE_ID} row: {path}")
        return
    item = matches[0]
    expected = {
        "title": PACKAGE_TITLE,
        "task": PACKAGE_TASK,
        "milestone_id": MILESTONE_ID,
        "repo": PACKAGE_REPO,
        "status": PACKAGE_STATUS,
        "wave": PACKAGE_WAVE,
        "completion_action": PACKAGE_COMPLETION_ACTION,
        "do_not_reopen_reason": PACKAGE_DO_NOT_REOPEN_REASON,
    }
    for key, value in expected.items():
        if item.get(key) != value:
            errors.append(f"{label} {PACKAGE_ID} {key} must be {value!r}: {path}")
    if str(item.get("work_task_id")) != WORK_TASK_ID:
        errors.append(f"{label} {PACKAGE_ID} work_task_id must be {WORK_TASK_ID!r}: {path}")
    if sorted(item.get("allowed_paths") or []) != sorted(ALLOWED_PATHS):
        errors.append(f"{label} {PACKAGE_ID} allowed_paths drifted: {path}")
    if sorted(item.get("owned_surfaces") or []) != sorted(OWNED_SURFACES):
        errors.append(f"{label} {PACKAGE_ID} owned_surfaces drifted: {path}")
    reject_forbidden_markers(json.dumps(item, sort_keys=True), f"{label} {PACKAGE_ID}", errors)


def verify_successor_registry(errors: list[str], path: Path) -> None:
    payload = load_yaml(path, label="successor registry")
    milestones = payload.get("milestones")
    if not isinstance(milestones, list):
        errors.append(f"successor registry milestones must be a list: {path}")
        return
    milestone = next((item for item in milestones if isinstance(item, dict) and item.get("id") == MILESTONE_ID), None)
    if not isinstance(milestone, dict):
        errors.append(f"successor registry missing milestone {MILESTONE_ID}: {path}")
        return
    if milestone.get("title") != "Rule-environment studio and explain receipts everywhere":
        errors.append(f"successor registry milestone {MILESTONE_ID} title drifted: {path}")
    if milestone.get("status") != "in_progress":
        errors.append(f"successor registry milestone {MILESTONE_ID} status must stay in_progress: {path}")
    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        errors.append(f"successor registry milestone {MILESTONE_ID} work_tasks must be a list: {path}")
        return
    task = next((item for item in work_tasks if isinstance(item, dict) and str(item.get("id")) == WORK_TASK_ID), None)
    if not isinstance(task, dict):
        errors.append(f"successor registry missing work task {WORK_TASK_ID}: {path}")
        return
    if task.get("owner") != PACKAGE_REPO:
        errors.append(f"successor registry work task {WORK_TASK_ID} owner must be {PACKAGE_REPO}: {path}")
    if str(task.get("title") or "").rstrip(".") != PACKAGE_TITLE.rstrip("."):
        errors.append(f"successor registry work task {WORK_TASK_ID} title drifted: {path}")
    if task.get("status") != PACKAGE_STATUS:
        errors.append(f"successor registry work task {WORK_TASK_ID} status must be {PACKAGE_STATUS}: {path}")
    evidence = task.get("evidence")
    if not isinstance(evidence, list):
        errors.append(f"successor registry work task {WORK_TASK_ID} evidence must be a list: {path}")
    else:
        evidence_text = "\n".join(str(item) for item in evidence)
        for marker in (
            "CampaignSpineService.cs projects rules navigator answers with stable ExplainEntryId values",
            "SupportAssistantService.cs forwards RulesNavigator ExplainEntryId values into support citations",
            "python3 scripts/verify_next90_m114_hub_rule_environment_receipts.py exits 0.",
            "python3 -m unittest tests/test_next90_m114_hub_rule_environment_receipts.py exits 0",
        ):
            if marker not in evidence_text:
                errors.append(f"successor registry work task {WORK_TASK_ID} evidence missing marker {marker!r}: {path}")
    reject_forbidden_markers(json.dumps(task, sort_keys=True), f"successor registry {WORK_TASK_ID}", errors)


def verify_release_proof(errors: list[str], path: Path, *, label: str) -> None:
    if not path.is_file():
        errors.append(f"{label} is missing: {path}")
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{label} is not valid JSON: {path} ({exc})")
        return
    if not isinstance(payload, dict):
        errors.append(f"{label} must be a JSON object: {path}")
        return

    package = ((payload.get("successor_queue_packages_by_id") or {}).get(PACKAGE_ID))
    if not isinstance(package, dict):
        errors.append(f"{label} missing successor_queue_packages_by_id[{PACKAGE_ID!r}]: {path}")
    else:
        for key, value in LOCAL_RELEASE_PROOF_PACKAGE.items():
            if key == "owned_surfaces":
                if sorted(package.get(key) or []) != sorted(value):
                    errors.append(f"{label} package {PACKAGE_ID} {key} must be {value!r}: {path}")
                continue
            if package.get(key) != value:
                errors.append(f"{label} package {PACKAGE_ID} {key} must be {value!r}: {path}")

    receipts = payload.get("proof_receipts")
    if not isinstance(receipts, list):
        errors.append(f"{label} must expose proof_receipts[]: {path}")
        return

    package_rows = [
        receipt
        for receipt in receipts
        if isinstance(receipt, dict) and receipt.get("package_id") == PACKAGE_ID
    ]
    if len(package_rows) != len(LOCAL_RELEASE_PROOF_RECEIPTS):
        errors.append(
            f"{label} must expose exactly {len(LOCAL_RELEASE_PROOF_RECEIPTS)} {PACKAGE_ID} proof receipts: {path}"
        )

    receipt_ids = [str(receipt.get("receipt_id") or "") for receipt in package_rows]
    duplicate_receipt_ids = sorted({receipt_id for receipt_id in receipt_ids if receipt_ids.count(receipt_id) > 1})
    if duplicate_receipt_ids:
        errors.append(f"{label} has duplicate {PACKAGE_ID} receipt ids {duplicate_receipt_ids!r}: {path}")

    receipt_by_id = {
        receipt.get("receipt_id"): receipt
        for receipt in receipts
        if isinstance(receipt, dict) and receipt.get("package_id") == PACKAGE_ID
    }
    for receipt_id, expected in LOCAL_RELEASE_PROOF_RECEIPTS.items():
        receipt = receipt_by_id.get(receipt_id)
        if not isinstance(receipt, dict):
            errors.append(f"{label} missing proof receipt {receipt_id}: {path}")
            continue
        for key in ("package_id", "milestone_id", "frontier_id"):
            if receipt.get(key) != expected[key]:
                errors.append(f"{label} receipt {receipt_id}.{key} must be {expected[key]!r}: {path}")
        if receipt.get("routes") != expected["routes"]:
            errors.append(f"{label} receipt {receipt_id}.routes must stay {expected['routes']!r}: {path}")
        if receipt.get("surfaces") != expected["surfaces"]:
            errors.append(f"{label} receipt {receipt_id}.surfaces must stay {expected['surfaces']!r}: {path}")
        summary = str(receipt.get("summary") or "").casefold()
        for marker in expected["summary_markers"]:
            if marker.casefold() not in summary:
                errors.append(f"{label} receipt {receipt_id} summary missing marker {marker!r}: {path}")
        evidence = receipt.get("evidence")
        if not isinstance(evidence, list):
            errors.append(f"{label} receipt {receipt_id}.evidence must be a list: {path}")
        else:
            evidence_text = "\n".join(str(item) for item in evidence)
            for marker in expected["evidence_markers"]:
                if marker not in evidence_text:
                    errors.append(f"{label} receipt {receipt_id} evidence missing marker {marker!r}: {path}")
        reject_forbidden_markers(json.dumps(receipt, sort_keys=True), f"{label} receipt {receipt_id}", errors)


def main() -> int:
    errors: list[str] = []
    verify_source_markers(errors)
    verify_queue_row(errors, FLEET_QUEUE_STAGING_PATH, label="fleet queue")
    verify_queue_row(errors, DESIGN_QUEUE_STAGING_PATH, label="design queue")
    verify_successor_registry(errors, SUCCESSOR_REGISTRY_PATH)
    verify_release_proof(errors, LOCAL_RELEASE_PROOF_PATH, label="repo-local release proof")
    verify_release_proof(errors, SERVED_RELEASE_PROOF_PATH, label="served release proof")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("rule-environment receipt proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
