#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m119-hub-first-session-onboarding"
WORK_TASK_ID = "119.1"
FRONTIER_ID = 1130567614
MILESTONE_ID = 119
PACKAGE_TITLE = "Orchestrate guided first-playable-session onboarding"
PACKAGE_TASK = "Join install, claim, campaign primer, starter build, briefing, and support-safe recovery into a measured first-session path."
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W14"
PACKAGE_STATUS = "complete"
PACKAGE_LANDED_COMMIT = "TO_BE_FILLED_M119_COMMIT"
PACKAGE_COMPLETION_ACTION = "verify_closed_package_only"
PACKAGE_DO_NOT_REOPEN_REASON = (
    "M119 chummer6-hub guided first-playable-session onboarding is complete; future shards must verify "
    "the first-session records, local release package, canonical registry row, Fleet queue row, and design "
    "queue row instead of reopening the install-to-first-session onboarding slice."
)
OWNED_SURFACES = {
    "first_playable_session:onboarding",
    "starter_lane:hub",
}
ALLOWED_PATHS = {"Chummer.Run.Api", "scripts", "tests"}
REQUIRED_PROOF = [
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Landing.cshtml",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Home.cshtml",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/Accounts/Account.cshtml",
    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs",
    "/docker/chummercomplete/chummer6-hub/scripts/materialize_hub_local_release_proof.py",
    "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m119_hub_first_session_onboarding.py",
    "/docker/chummercomplete/chummer6-hub/tests/test_next90_m119_hub_first_session_onboarding.py",
    "python3 scripts/verify_next90_m119_hub_first_session_onboarding.py",
    "python3 -m unittest tests/test_next90_m119_hub_first_session_onboarding.py",
    "bash scripts/ai/run_services_smoke.sh",
]
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
    "landed_commit": PACKAGE_LANDED_COMMIT,
    "completion_action": PACKAGE_COMPLETION_ACTION,
    "do_not_reopen_reason": PACKAGE_DO_NOT_REOPEN_REASON,
    "allowed_paths": sorted(ALLOWED_PATHS),
    "owned_surfaces": sorted(OWNED_SURFACES),
    "proof": REQUIRED_PROOF,
    "exit_criterion": PACKAGE_TASK,
}
LOCAL_RELEASE_PROOF_RECEIPTS = {
    "first_playable_session:onboarding": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/home",
            "/home/work",
            "/account/work",
            "/account/roster",
            "/api/v1/campaign-spine/me",
            "/api/v1/campaign-spine/me/workspaces/starter",
        ],
        "surfaces": [
            "first_playable_session:onboarding",
            "campaign_onboarding",
            "install_claim_restore_continue",
        ],
        "summary_markers": [
            "first-session workspace seeding",
            "campaign-primer-backed first-session detail",
            "support-safe recovery",
        ],
        "evidence_markers": [
            "CampaignSpineController.cs exposes the starter-workspace seeding route",
            "CampaignSpineService.cs projects first-playable-session summaries",
            "RunServicesSmoke/Program.cs checks landing, home, account, and starter-workspace API surfaces",
        ],
    },
    "starter_lane:hub": {
        "package_id": PACKAGE_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "routes": [
            "/home/work",
            "/account/work",
            "/account/roster",
            "/account/access",
            "/contact",
        ],
        "surfaces": [
            "starter_lane:hub",
            "first_session:proof_drawer",
            "starter_build:follow_through",
        ],
        "summary_markers": [
            "linked install",
            "first-session detail",
            "install support",
        ],
        "evidence_markers": [
            "Views/PublicLanding/Home.cshtml wires first-session workspace seeding",
            "Views/Accounts/Account.cshtml keeps the selected first-session drawer",
            "PublicLandingController.cs promotes first-session work as the primary signed-in action",
        ],
    },
}
SOURCE_MARKERS = {
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs": [
        '[HttpPost("me/workspaces/starter")]',
        "public async Task<ActionResult<CampaignWorkspaceProjection>> SeedStarterWorkspace",
        "CampaignWorkspaceProjection? starter = _campaignSpine.GetStarterWorkspace(user, installLinking);",
    ],
    "Chummer.Run.Api/Controllers/PublicLandingController.cs": [
        '"First session",',
        '"Open campaigns and start your first playable session"',
        '"Open campaigns",',
        '"/account/roster",',
    ],
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs": [
        'Label: "First playable session"',
        "BuildFirstPlayableRuleReadySummary(",
        "BuildFirstPlayableReturnLaneSummary(",
        "BuildFirstPlayableCampaignReadySummary(",
        '"primer" => $"{workspace.CampaignName} campaign primer"',
        '"primer" => "Primer-safe onboarding, campaign continuity, and governed publication detail stay attached to one shared artifact lane."',
    ],
    "Chummer.Run.Api/Views/PublicLanding/Landing.cshtml": [
        'var entryHref = Model.Chrome.Authenticated ? "/account" : "/login?next=%2Faccount%2Faccess";',
        '<span class="site-account-menu__label">Open Chummer</span>',
        'href="/build"',
        'href="/help"',
    ],
    "Chummer.Run.Api/Views/PublicLanding/Home.cshtml": [
        'id="seedStarterWorkspace"',
        "/api/v1/campaign-spine/me/workspaces/starter",
        "Open first playable session",
        "Rules: @leadFirstPlayableSession.RuleReadySummary",
        "Return: @leadFirstPlayableSession.ReturnLaneSummary",
        "Ready: @leadFirstPlayableSession.CampaignReadySummary",
        "Open build path for @PublicText(handoff.Title)",
    ],
    "Chummer.Run.Api/Views/Accounts/Account.cshtml": [
        'id="selected-first-playable-session"',
        "Start first playable session",
        "Open Home",
        "Open install support",
        "<p><strong>Legal runner:</strong> @selectedWorkspaceFirstPlayableSession.RuleReadySummary</p>",
        "<p><strong>Understandable return:</strong> @selectedWorkspaceFirstPlayableSession.ReturnLaneSummary</p>",
        "<p><strong>Campaign readiness:</strong> @selectedWorkspaceFirstPlayableSession.CampaignReadySummary</p>",
    ],
    "tests/RunServicesSmoke/Program.cs": [
        'Assert(landingSource.Contains("Model.Chrome.Authenticated ? \\"/account\\"", StringComparison.Ordinal), "landing should keep a direct authenticated route from the front door into account continuity.");',
        'Assert(homeSource.Contains("seedStarterWorkspace", StringComparison.Ordinal), "home work should include starter-lane seeding on the empty workspace first-run path.");',
        'Assert(accountSource.Contains("Start first playable session", StringComparison.Ordinal), "account work should offer starter-lane follow-through when the shared campaign view is still empty.");',
        'Assert(accountModel.CampaignSpine.CreatorPublications.Any(item => string.Equals(item.Kind, "primer", StringComparison.Ordinal) && item.Title.Contains("campaign primer", StringComparison.OrdinalIgnoreCase)), "account page should surface a first-class primer publication alongside the existing shared publication lanes.");',
        'Assert(starterWorkspacePayload!.FirstPlayableSession is not null, "campaign spine starter api should return first-session proof on the starter workspace payload.");',
    ],
    "scripts/materialize_hub_local_release_proof.py": [
        '"package_id": "next90-m119-hub-first-session-onboarding"',
        '"work_task_id": "119.1"',
        '"receipt_id": "first_playable_session:onboarding"',
        '"receipt_id": "starter_lane:hub"',
    ],
    "scripts/verify_next90_m119_hub_first_session_onboarding.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        "LOCAL_RELEASE_PROOF_RECEIPTS = {",
        'print("next90 m119 hub first-session onboarding proof passed")',
    ],
    "tests/test_hub_local_release_proof_native_support_route.py": [
        "test_materialized_m119_proof_includes_first_session_onboarding_receipts",
        "first_playable_session:onboarding",
        "starter_lane:hub",
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_next90_m119_hub_first_session_onboarding.py",
        "python3 -m unittest tests/test_next90_m119_hub_first_session_onboarding.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M119_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M119_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M119_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M119_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)
LOCAL_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M119_LOCAL_RELEASE_PROOF",
        str(ROOT / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"),
    )
)
SERVED_RELEASE_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M119_SERVED_RELEASE_PROOF",
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
    text = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        if "queue" not in label:
            raise
        payload = load_queue_staging_yaml(text, label=label, path=path)
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} is not a YAML mapping: {path}")
    return payload


def load_queue_staging_yaml(text: str, *, label: str, path: Path) -> dict:
    package_marker = f"package_id: {PACKAGE_ID}"
    package_index = text.find(package_marker)
    if package_index < 0:
        raise SystemExit(f"{label} is missing package_id {PACKAGE_ID}: {path}")

    start = text.rfind("\n- title:", 0, package_index)
    if start < 0:
        if not text.startswith("- title:"):
            raise SystemExit(f"{label} is missing the item block for {PACKAGE_ID}: {path}")
        start = 0
    else:
        start += 1

    end = text.find("\n- title:", package_index)
    if end < 0:
        end = len(text)

    block = text[start:end].rstrip() + "\n"
    try:
        payload = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        raise SystemExit(f"{label} is not a YAML mapping: {path}") from exc
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise SystemExit(f"{label} package block did not parse correctly: {path}")
    return {"items": payload}


def verify_queue_row(errors: list[str], path: Path, *, label: str) -> None:
    payload = load_yaml(path, label=label)
    items = payload.get("items")
    if not isinstance(items, list):
        errors.append(f"{label} items list is missing: {path}")
        return

    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        errors.append(f"{label} expected exactly one {PACKAGE_ID} row, found {len(matches)}")
        return

    row = matches[0]
    expected_fields = {
        "title": PACKAGE_TITLE,
        "task": PACKAGE_TASK,
        "repo": PACKAGE_REPO,
        "work_task_id": 119.1,
        "milestone_id": MILESTONE_ID,
        "status": PACKAGE_STATUS,
        "wave": PACKAGE_WAVE,
        "landed_commit": PACKAGE_LANDED_COMMIT,
        "completion_action": PACKAGE_COMPLETION_ACTION,
        "do_not_reopen_reason": PACKAGE_DO_NOT_REOPEN_REASON,
    }
    for key, value in expected_fields.items():
        if row.get(key) != value:
            errors.append(f"{label} {PACKAGE_ID} {key} must be {value!r}")
    if row.get("allowed_paths") != sorted(ALLOWED_PATHS):
        errors.append(f"{label} {PACKAGE_ID} allowed_paths must be {sorted(ALLOWED_PATHS)!r}")
    if row.get("owned_surfaces") != sorted(OWNED_SURFACES):
        errors.append(f"{label} {PACKAGE_ID} owned_surfaces must be {sorted(OWNED_SURFACES)!r}")
    if row.get("proof") != REQUIRED_PROOF:
        errors.append(f"{label} {PACKAGE_ID} proof must match the completed package receipt exactly")


def verify_successor_registry(errors: list[str]) -> None:
    payload = load_yaml(SUCCESSOR_REGISTRY_PATH, label="successor registry")
    milestones = payload.get("milestones")
    if not isinstance(milestones, list):
        errors.append(f"successor registry milestones list is missing: {SUCCESSOR_REGISTRY_PATH}")
        return

    milestone = next((item for item in milestones if isinstance(item, dict) and item.get("id") == MILESTONE_ID), None)
    if milestone is None:
        errors.append(f"successor registry missing milestone {MILESTONE_ID}")
        return

    if milestone.get("title") != "Guided onboarding to first playable session":
        errors.append("successor registry milestone 119 title drifted")

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        errors.append("successor registry milestone 119 work_tasks list is missing")
        return

    task = next((item for item in work_tasks if isinstance(item, dict) and str(item.get("id")) == WORK_TASK_ID), None)
    if task is None:
        errors.append(f"successor registry missing work task {WORK_TASK_ID}")
        return

    if task.get("owner") != PACKAGE_REPO:
        errors.append("successor registry work task 119.1 owner drifted")
    if task.get("title") != "Orchestrate guided first-session onboarding from install, claim, campaign, primer, starter build, and support truth.":
        errors.append("successor registry work task 119.1 title drifted")


def load_json(path: Path, *, label: str) -> dict:
    if not path.is_file():
        raise SystemExit(f"{label} is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} is not a JSON object: {path}")
    return payload


def verify_release_proof(errors: list[str], path: Path, *, label: str) -> None:
    payload = load_json(path, label=label)
    text = json.dumps(payload, sort_keys=True)
    reject_forbidden_markers(text, label, errors)

    packages = payload.get("successor_queue_packages_by_id")
    if not isinstance(packages, dict):
        errors.append(f"{label} successor_queue_packages_by_id is missing")
        return

    package = packages.get(PACKAGE_ID)
    if not isinstance(package, dict):
        errors.append(f"{label} missing package {PACKAGE_ID}")
    else:
        for key, expected_value in LOCAL_RELEASE_PROOF_PACKAGE.items():
            if package.get(key) != expected_value:
                errors.append(f"{label} package {PACKAGE_ID} {key} must be {expected_value!r}")

    receipts = payload.get("proof_receipts")
    if not isinstance(receipts, list):
        errors.append(f"{label} proof_receipts is missing")
        return

    receipts_by_id = {
        receipt.get("receipt_id"): receipt
        for receipt in receipts
        if isinstance(receipt, dict)
    }
    for receipt_id, expected in LOCAL_RELEASE_PROOF_RECEIPTS.items():
        receipt = receipts_by_id.get(receipt_id)
        if not isinstance(receipt, dict):
            errors.append(f"{label} missing receipt {receipt_id}")
            continue
        if receipt.get("package_id") != expected["package_id"]:
            errors.append(f"{label} receipt {receipt_id} package_id drifted")
        if receipt.get("milestone_id") != expected["milestone_id"]:
            errors.append(f"{label} receipt {receipt_id} milestone_id drifted")
        if receipt.get("frontier_id") != expected["frontier_id"]:
            errors.append(f"{label} receipt {receipt_id} frontier_id drifted")
        routes = receipt.get("routes") or []
        for route in expected["routes"]:
            if route not in routes:
                errors.append(f"{label} receipt {receipt_id} missing route {route}")
        surfaces = receipt.get("surfaces") or []
        for surface in expected["surfaces"]:
            if surface not in surfaces:
                errors.append(f"{label} receipt {receipt_id} missing surface {surface}")
        summary = str(receipt.get("summary") or "")
        for marker in expected["summary_markers"]:
            if marker not in summary:
                errors.append(f"{label} receipt {receipt_id} summary missing marker {marker!r}")
        evidence_lines = " ".join(str(item) for item in (receipt.get("evidence") or []))
        for marker in expected["evidence_markers"]:
            if marker not in evidence_lines:
                errors.append(f"{label} receipt {receipt_id} evidence missing marker {marker!r}")


def main() -> int:
    errors: list[str] = []
    verify_queue_row(errors, FLEET_QUEUE_STAGING_PATH, label="fleet queue")
    verify_queue_row(errors, DESIGN_QUEUE_STAGING_PATH, label="design queue")
    verify_successor_registry(errors)
    verify_release_proof(errors, LOCAL_RELEASE_PROOF_PATH, label="repo-local release proof")
    verify_release_proof(errors, SERVED_RELEASE_PROOF_PATH, label="served release proof")
    verify_source_markers(errors)

    if errors:
        for item in errors:
            print(item, file=sys.stderr)
        return 1

    print("next90 m119 hub first-session onboarding proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
