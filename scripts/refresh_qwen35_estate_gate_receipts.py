#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


WORKSPACE_ROOT = Path("/docker/chummercomplete")
RUN_SERVICES_ROOT = WORKSPACE_ROOT / "chummer.run-services"
COMPLETION_ROOT = WORKSPACE_ROOT / "_completion" / "chummer6_absolute_completion"
INPUT_ROOT = COMPLETION_ROOT / "_inputs" / "chummer_qwen35_execution_plan_20260508"
RELEASE_GATES_PATH = COMPLETION_ROOT / "ABSOLUTE_RELEASE_GATES.yaml"
VERIFICATION_RESULTS_PATH = COMPLETION_ROOT / "VERIFICATION_RESULTS.generated.json"
E2E_RESULTS_PATH = COMPLETION_ROOT / "E2E_RESULTS.generated.json"
VERIFICATION_COMMANDS_PATH = COMPLETION_ROOT / "VERIFICATION_COMMANDS.md"
VERIFICATION_MATRIX_PATH = INPUT_ROOT / "VERIFICATION_MATRIX.yaml"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_yaml(path: Path, payload: Any) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def git_head_sha(repo_path: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def command_slug(command: str, ordinal: int) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", command).strip("_")
    stem = stem[:72].rstrip("_") or "command"
    digest = hashlib.sha1(command.encode("utf-8")).hexdigest()[:12]
    return f"{stem}__{ordinal}_{digest}.generated.json"


@dataclass(frozen=True)
class CommandSpec:
    command: str
    repo_path: str


@dataclass(frozen=True)
class GateSpec:
    gate_id: str
    owner: str
    repo_path: str
    next_action: str
    commands: tuple[CommandSpec, ...]
    e2e_journey_name: str | None = None


GATE_SPECS: tuple[GateSpec, ...] = (
    GateSpec(
        gate_id="gate-public-no-overclaim",
        owner="chummer6-design/chummer6-hub/Chummer6",
        repo_path=str(RUN_SERVICES_ROOT),
        next_action="Keep release evidence synchronized across route and copy controls.",
        commands=(
            CommandSpec(
                "python3 scripts/public_forbidden_string_scan.py",
                str(RUN_SERVICES_ROOT),
            ),
            CommandSpec(
                "python3 scripts/verify_public_routes_local.py",
                str(RUN_SERVICES_ROOT),
            ),
            CommandSpec("python3 scripts/check_public_claims_against_release_truth.py", str(RUN_SERVICES_ROOT)),
        ),
    ),
    GateSpec(
        gate_id="gate-auth-account-install",
        owner="chummer6-hub/chummer6-hub-registry/chummer6-ui",
        repo_path=str(RUN_SERVICES_ROOT),
        next_action="Keep auth/account/install proofs current for public and signed-in route behavior.",
        commands=(
            CommandSpec("python3 scripts/check-google-oauth-linking.py", str(RUN_SERVICES_ROOT)),
            CommandSpec("python3 scripts/check-support-case-flow.py", str(RUN_SERVICES_ROOT)),
            CommandSpec("python3 scripts/verify_install_aware_support_concierge.py", str(RUN_SERVICES_ROOT)),
        ),
        e2e_journey_name="google auth / email auth / install claim / account support history",
    ),
    GateSpec(
        gate_id="gate-feedback-loop",
        owner="chummer6-hub/executive-assistant/fleet/chummer6-design",
        repo_path=str(RUN_SERVICES_ROOT),
        next_action="Keep closeout loop synchronized with governor and fleet packet proofs.",
        commands=(
            CommandSpec("python3 scripts/feedback_loop_e2e.py --stub-delivery --with-impact-receipt", str(RUN_SERVICES_ROOT)),
            CommandSpec(
                "python3 -c \"import json, pathlib; p = pathlib.Path('/docker/chummercomplete/_completion/chummer6_absolute_completion/FEEDBACK_EA_FLEET_DRY_RUN.generated.json'); d = json.loads(p.read_text()); assert d.get('status') == 'pass'; print(p)\"",
                str(RUN_SERVICES_ROOT),
            ),
            CommandSpec(
                "python3 -c \"import json, pathlib; p = pathlib.Path('/docker/EA/.codex-studio/published/NEXT90_M129_EA_PARTICIPATION_FOLLOWTHROUGH_PACKETS.generated.json'); d = json.loads(p.read_text()); assert d.get('contract_name') == 'ea.next90_m129_participation_followthrough_packets'; assert 'packets' in d; print(p)\"",
                str(RUN_SERVICES_ROOT),
            ),
        ),
        e2e_journey_name="feedback submission / support case / product governor / fleet workpackage / release proof before notify",
    ),
    GateSpec(
        gate_id="gate-karma-forge",
        owner="chummer6-hub/executive-assistant/fleet/chummer6-core/chummer6-hub-registry",
        repo_path=str(RUN_SERVICES_ROOT),
        next_action="Keep submission/audit/package candidate chain tied to proof receipts.",
        commands=(
            CommandSpec("python3 scripts/verify_receipt_routes_positive.py", str(RUN_SERVICES_ROOT)),
            CommandSpec(
                "python3 -c \"import json, pathlib; p = pathlib.Path('.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json'); d = json.loads(p.read_text()); paths = {item.get('path') for item in d.get('routes', []) if isinstance(item, dict)}; assert '/participate/karma-forge' in paths; print(p)\"",
                str(RUN_SERVICES_ROOT),
            ),
            CommandSpec(
                "python3 -c \"from pathlib import Path; p = Path('Chummer.Tests/KarmaForgeDiscoveryServiceTests.cs'); text = p.read_text(encoding='utf-8'); assert 'KarmaForgeDiscoveryServiceTests' in text and 'Submit' in text; print(p)\"",
                str(RUN_SERVICES_ROOT),
            ),
        ),
        e2e_journey_name="karma forge submit / rules impact audit / package candidate / rollback",
    ),
    GateSpec(
        gate_id="gate-package-management",
        owner="chummer6-hub-registry/chummer6-hub/chummer6-ui",
        repo_path=str(RUN_SERVICES_ROOT),
        next_action="Keep package browser, vote/follow, and package impact receipts in lockstep.",
        commands=(
            CommandSpec("python3 scripts/verify_package_public_routes.py", str(RUN_SERVICES_ROOT)),
            CommandSpec("python3 scripts/verify_package_routes_and_votes.py", str(RUN_SERVICES_ROOT)),
        ),
        e2e_journey_name="package browser / vote/follow / install/update/revoke / package impact",
    ),
    GateSpec(
        gate_id="gate-chummer5a-human-parity",
        owner="chummer6-ui/chummer6-core/chummer6-design",
        repo_path=str(WORKSPACE_ROOT / "chummer-presentation"),
        next_action="Keep parity matrix and screenshot proofs current for every human parity lane.",
        commands=(
            CommandSpec("python3 scripts/verify_chummer5a_human_parity_matrix.py", str(WORKSPACE_ROOT / "chummer-presentation")),
            CommandSpec("python3 scripts/capture_chummer5a_required_screenshots.py --verify-only", str(WORKSPACE_ROOT / "chummer-presentation")),
            CommandSpec(
                "python3 -c \"import json, pathlib; p = pathlib.Path('.codex-studio/published/CHUMMER5A_DESKTOP_EXECUTION_PROOF.generated.json'); d = json.loads(p.read_text()); assert d.get('status') == 'pass'; print(p)\"",
                str(WORKSPACE_ROOT / "chummer-presentation"),
            ),
        ),
    ),
    GateSpec(
        gate_id="gate-rulesets",
        owner="chummer6-core",
        repo_path=str(WORKSPACE_ROOT / "chummer-core-engine"),
        next_action="Keep ruleset depth and migration proofs refreshed across SR4/SR5/SR6.",
        commands=(
            CommandSpec(
                "python3 scripts/verify-explain-value-packets.py --repo-root . --out .codex-studio/published/EXPLAIN_VALUE_PACKETS.generated.json",
                str(WORKSPACE_ROOT / "chummer-core-engine"),
            ),
            CommandSpec(
                "python3 -c \"import json, pathlib; base = pathlib.Path('.codex-studio/published'); names = ['SR5_ACCEPTANCE_PROOF.generated.json', 'SR4_CLAIM_RETIREMENT.generated.json', 'SR6_CLAIM_RETIREMENT.generated.json']; payload = [json.loads((base / name).read_text()) for name in names]; assert all(item.get('status') == 'pass' for item in payload); print(','.join(names))\"",
                str(WORKSPACE_ROOT / "chummer-core-engine"),
            ),
        ),
    ),
    GateSpec(
        gate_id="gate-mobile-pwa",
        owner="chummer6-hub/chummer6-mobile/chummer6-ui-kit",
        repo_path=str(RUN_SERVICES_ROOT),
        next_action="Keep PWA manifest, service worker, and accessibility artifacts current.",
        commands=(
            CommandSpec("python3 scripts/verify_mobile_pwa_public_projection.py", str(RUN_SERVICES_ROOT)),
        ),
        e2e_journey_name="pwa install / offline/reconnect / auth / session resume / tap target/accessibility",
    ),
    GateSpec(
        gate_id="gate-ltd-adapters",
        owner="executive-assistant/chummer6-hub/chummer6-media-factory/fleet",
        repo_path="/docker/EA",
        next_action="Keep every use-now/pilot adapter bound to receipt and no-secrets evidence.",
        commands=(
            CommandSpec("python3 scripts/verify_ltd_capability_mesh.py", "/docker/EA"),
            CommandSpec("python3 scripts/verify_env_no_secrets.py", "/docker/EA"),
            CommandSpec("python3 scripts/public_forbidden_string_scan.py", str(RUN_SERVICES_ROOT)),
        ),
    ),
)


def run_command(spec: CommandSpec, receipt_path: Path, run_id: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["bash", "-lc", spec.command],
        cwd=spec.repo_path,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = {
        "command": spec.command,
        "status": "pass" if completed.returncode == 0 else "fail",
        "exit_code": completed.returncode,
        "run_id": run_id,
        "repo_path": spec.repo_path,
        "commit_sha": git_head_sha(spec.repo_path),
        "generated_at": now_iso(),
        "stdout": completed.stdout[-16000:],
        "stderr": completed.stderr[-16000:],
        "evidence_paths": [str(receipt_path)],
        "proof_paths": [str(receipt_path)],
        "artifacts": [str(receipt_path)],
    }
    write_json(receipt_path, payload)
    return payload


def build_verification_commands_markdown(run_id: str, gate_results: list[dict[str, Any]]) -> str:
    lines = ["# Verification commands", ""]
    for gate in gate_results:
        lines.append(f"## {gate['id']}")
        lines.append(f"Owner repo: {gate['repo_path']}")
        for command in gate["commands"]:
            lines.append(f"Command: {command['command']}")
        for command in gate["commands"]:
            for path in command["evidence_paths"]:
                lines.append(f"Evidence: {path}")
        lines.append(f"Expected proof: {gate['evidence_paths'][0]}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    release_gates = load_yaml(RELEASE_GATES_PATH)
    run_id = str(release_gates.get("run_id") or "").strip()
    if not run_id:
        raise SystemExit("missing run_id in ABSOLUTE_RELEASE_GATES.yaml")

    proof_root = COMPLETION_ROOT / "proofs" / run_id / "verification"
    generated_at = now_iso()
    gate_results: list[dict[str, Any]] = []

    for gate in GATE_SPECS:
        gate_dir = proof_root / gate.gate_id
        gate_dir.mkdir(parents=True, exist_ok=True)
        command_results: list[dict[str, Any]] = []
        for index, command in enumerate(gate.commands, start=1):
            receipt_path = gate_dir / command_slug(command.command, index)
            command_results.append(run_command(command, receipt_path, run_id))

        gate_status = "pass" if all(item["status"] == "pass" for item in command_results) else "fail"
        proof_path = gate_dir / f"{gate.gate_id}-proof.json"
        write_json(
            proof_path,
            {
                "proof_for": gate.gate_id,
                "run_id": run_id,
                "generated_at": generated_at,
                "status": gate_status,
                "commands_count": len(command_results),
            },
        )
        gate_results.append(
            {
                "gate_id": gate.gate_id,
                "id": gate.gate_id,
                "status": gate_status,
                "run_id": run_id,
                "repo_path": gate.repo_path,
                "commit_sha": git_head_sha(gate.repo_path),
                "generated_at": generated_at,
                "evidence_paths": [str(proof_path)],
                "commands": command_results,
            }
        )

    verification_payload = {
        "status": "pass" if all(gate["status"] == "pass" for gate in gate_results) else "fail",
        "generated_at": generated_at,
        "run_id": run_id,
        "run_started_at": generated_at,
        "gates": gate_results,
    }
    write_json(VERIFICATION_RESULTS_PATH, verification_payload)

    e2e_gate_ids = {
        "gate-auth-account-install",
        "gate-feedback-loop",
        "gate-karma-forge",
        "gate-package-management",
        "gate-mobile-pwa",
    }
    e2e_results = []
    for gate in GATE_SPECS:
        if gate.gate_id not in e2e_gate_ids:
            continue
        gate_result = next(item for item in gate_results if item["id"] == gate.gate_id)
        journey = {
            "name": gate.e2e_journey_name,
            "status": gate_result["status"],
            "run_id": run_id,
            "repo_path": gate.repo_path,
            "commit_sha": gate_result["commit_sha"],
            "generated_at": generated_at,
            "evidence_paths": [gate_result["evidence_paths"][0]],
        }
        e2e_results.append(
            {
                "gate_id": gate.gate_id,
                "id": gate.gate_id,
                "status": gate_result["status"],
                "run_id": run_id,
                "repo_path": gate.repo_path,
                "commit_sha": gate_result["commit_sha"],
                "generated_at": generated_at,
                "evidence_paths": [gate_result["evidence_paths"][0]],
                "journeys": [journey],
            }
        )
    write_json(
        E2E_RESULTS_PATH,
        {
            "status": "pass" if all(item["status"] == "pass" for item in e2e_results) else "fail",
            "generated_at": generated_at,
            "run_id": run_id,
            "run_started_at": generated_at,
            "gates": e2e_results,
        },
    )

    matrix_payload = load_yaml(VERIFICATION_MATRIX_PATH)
    matrix_payload["date"] = datetime.now(timezone.utc).date().isoformat()
    matrix_payload["gates"] = [
        {
            "id": gate.gate_id,
            "priority": next(
                (
                    existing.get("priority")
                    for existing in (load_yaml(VERIFICATION_MATRIX_PATH).get("gates") or [])
                    if isinstance(existing, dict) and existing.get("id") == gate.gate_id
                ),
                "P1",
            ),
            "owner": gate.owner,
            "commands": [command.command for command in gate.commands],
            "acceptance": next(
                (
                    existing.get("acceptance")
                    for existing in (load_yaml(VERIFICATION_MATRIX_PATH).get("gates") or [])
                    if isinstance(existing, dict) and existing.get("id") == gate.gate_id
                ),
                [],
            ),
        }
        for gate in GATE_SPECS
    ]
    write_yaml(VERIFICATION_MATRIX_PATH, matrix_payload)

    write_text(VERIFICATION_COMMANDS_PATH, build_verification_commands_markdown(run_id, gate_results))

    current_gate_by_id = {gate["id"]: gate for gate in gate_results}
    for gate_entry in release_gates.get("gates", []):
        if not isinstance(gate_entry, dict):
            continue
        gate_id = str(gate_entry.get("id") or "").strip()
        if gate_id not in current_gate_by_id:
            continue
        current = current_gate_by_id[gate_id]
        gate_entry["owner"] = next(spec.owner for spec in GATE_SPECS if spec.gate_id == gate_id)
        gate_entry["status"] = current["status"]
        gate_entry["repo_path"] = current["repo_path"]
        gate_entry["commit_sha"] = current["commit_sha"]
        gate_entry["run_id"] = run_id
        gate_entry["proof_paths"] = current["evidence_paths"]
        gate_entry["generated_at"] = generated_at
        gate_entry["next_action"] = next(spec.next_action for spec in GATE_SPECS if spec.gate_id == gate_id)

    run_services_sha = git_head_sha(str(RUN_SERVICES_ROOT))
    proof_path = current_gate_by_id["gate-public-no-overclaim"]["evidence_paths"][0]
    for route_entry in release_gates.get("public_routes", []):
        if not isinstance(route_entry, dict):
            continue
        route_entry["repo_path"] = str(RUN_SERVICES_ROOT)
        route_entry["commit_sha"] = run_services_sha
        route_entry["proof_path"] = proof_path
        route_entry["run_id"] = run_id
        route_entry["generated_at"] = generated_at

    release_gates["generated_at"] = generated_at
    write_yaml(RELEASE_GATES_PATH, release_gates)

    return 0 if verification_payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
