#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_context import OriginEditionContext


CONTRACT_NAME = "chummer.origin_edition.gold_proof_chain.v1"
DEFAULT_EVIDENCE_ROOT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold")
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EA_ROOT = Path("/docker/EA")


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: object) -> str:
    text = str(value or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def load_module(repo_root: Path, relative_path: str, module_name: str):
    path = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_modules(repo_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        deployed_probe=load_module(repo_root, "scripts/materialize_origin_dossier_deployed_browser_probe.py", "origin_deployed_probe"),
        handoff=load_module(repo_root, "scripts/materialize_origin_dossier_deployed_operator_handoff.py", "origin_deployed_handoff"),
        gold_audit=load_module(repo_root, "scripts/audit_origin_dossier_gold_e2e.py", "origin_gold_audit"),
        runsite=load_module(repo_root, "scripts/materialize_origin_edition_runsite_integration_proof.py", "origin_runsite_proof"),
        matrix=load_module(repo_root, "scripts/materialize_origin_edition_gold_completion_matrix.py", "origin_completion_matrix"),
        coverage=load_module(repo_root, "scripts/materialize_origin_edition_gold_requirement_coverage.py", "origin_requirement_coverage"),
    )


def stage(name: str, output: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "path": output.as_posix(),
        "sha256": sha256_file(output) if output.is_file() else "",
        "status": payload.get("status"),
        "goldEligible": payload.get("goldEligible"),
        "goalCompletionClaimAllowed": payload.get("goalCompletionClaimAllowed"),
        "blockers": payload.get("blockers", []),
        "blockedRows": payload.get("blockedRows", []),
        "blockedHardGates": payload.get("blockedHardGates", []),
        "blockedRequirements": payload.get("blockedRequirements", []),
        "failedCodes": payload.get("failedCodes", []),
        "next_action": payload.get("next_action"),
        "blocking_reason": payload.get("blocking_reason"),
        "progress": payload.get("progress", {}),
    }


def run_chain(
    *,
    repo_root: Path,
    ea_root: Path,
    evidence_root: Path,
    env_file: Path | None,
    output: Path,
    modules: SimpleNamespace | None = None,
    context: OriginEditionContext | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    ea_root = ea_root.resolve()
    evidence_root = evidence_root.resolve()
    modules = modules or load_modules(repo_root)
    context = context or OriginEditionContext.from_env(require_explicit=True)
    branch = context.branch(evidence_root)

    deployed_probe_path = branch / "deployed-chummer-browser-probe.receipt.json"
    deployed_probe = modules.deployed_probe.materialize(
        evidence_root,
        context.base_url,
        context.project_id,
        deployed_probe_path,
        env_file,
        context,
    )

    handoff_path = branch / "deployed-operator-handoff.receipt.json"
    handoff = modules.handoff.materialize(evidence_root, handoff_path, env_file, context)

    gold_audit_path = evidence_root / "ORIGIN_EDITION_GOLD_CURRENT_GAP_AUDIT.generated.json"
    gold_audit = modules.gold_audit.audit(
        live_import_request=evidence_root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json",
        ea_delivery_receipt=branch / "telegram-origin-link-bundle-live.receipt.json",
        browser_proof=deployed_probe_path,
        deployed_operator_handoff=handoff_path,
        output=gold_audit_path,
    )

    runsite_path = branch / "runsite-integration-proof.receipt.json"
    runsite = modules.runsite.materialize(repo_root, ea_root, evidence_root, runsite_path, context)

    matrix_path = evidence_root / "ORIGIN_EDITION_GOLD_COMPLETION_MATRIX.generated.json"
    matrix = modules.matrix.materialize(evidence_root, matrix_path, context)

    coverage_path = evidence_root / "ORIGIN_EDITION_GOLD_REQUIREMENT_COVERAGE.generated.json"
    coverage = modules.coverage.materialize(evidence_root, coverage_path)

    stages = [
        stage("deployed_browser_probe", deployed_probe_path, deployed_probe),
        stage("deployed_operator_handoff", handoff_path, handoff),
        stage("gold_gap_audit", gold_audit_path, gold_audit),
        stage("runsite_integration_proof", runsite_path, runsite),
        stage("completion_matrix", matrix_path, matrix),
        stage("requirement_coverage", coverage_path, coverage),
    ]
    blocked_requirements = sorted(
        {
            str(requirement).strip()
            for item in stages
            for requirement in item.get("blockedRequirements", [])
            if str(requirement).strip()
        }
    )
    passed = (
        matrix.get("status") == "pass"
        and matrix.get("goalCompletionClaimAllowed") is True
        and coverage.get("status") == "pass"
        and coverage.get("goalCompletionClaimAllowed") is True
    )
    blocking_reason = "" if passed else ",".join(
        str(item)
        for item in [
            *[f"stage:{stage_item['name']}" for stage_item in stages if stage_item.get("status") not in {"pass", "ready_for_operator_token"}],
            *[f"requirement:{requirement}" for requirement in blocked_requirements],
        ]
    )
    next_action = (
        "Gold proof chain is ready for release handoff. Keep the artifacts archived outside providers."
        if passed
        else str(deployed_probe.get("next_action") or handoff.get("next_action") or "Resolve blocked Gold proof stages and rerun the strict verifier.").strip()
    )
    progress = {
        "passedStages": sum(1 for item in stages if item.get("status") in {"pass", "ready_for_operator_token"}),
        "totalStages": len(stages),
        "blockedStages": [item["name"] for item in stages if item.get("status") not in {"pass", "ready_for_operator_token"}],
        "blockedRequirements": blocked_requirements,
    }
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "updated_at": now_iso(),
        "status": "pass" if passed else "blocked",
        "finalVerdict": "ORIGIN_EDITION_GOLD_READY" if passed else "ORIGIN_EDITION_GOLD_BLOCKED",
        "goalCompletionClaimAllowed": passed,
        "next_action": next_action,
        "blocking_reason": blocking_reason,
        "progress": progress,
        "namespace": context.resolved_namespace,
        "projectId": context.project_id,
        "context": {
            "familyName": context.family_name,
            "givenName": context.given_name,
            "runnerName": context.runner_name,
            "baseUrl": context.base_url,
        },
        "envFile": {
            "provided": env_file is not None,
            "pathSha256": sha256_text(env_file.as_posix()) if env_file is not None else "",
            "valuesStoredInReceipt": False,
        },
        "stages": stages,
        "blockedStages": progress["blockedStages"],
        "blockedRequirements": blocked_requirements,
        "privacy": {
            "rawCredentialExposed": False,
            "rawSessionTokenExposed": False,
            "envValuesExposed": False,
            "deploymentPerformed": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the secret-safe Origin Edition Gold proof chain.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--ea-root", type=Path, default=DEFAULT_EA_ROOT)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_REPO_ROOT / ".env")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--family-name")
    parser.add_argument("--given-name")
    parser.add_argument("--runner-name")
    parser.add_argument("--namespace")
    parser.add_argument("--base-url")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit zero after writing an honest blocked proof chain. Strict gold is enforced by verify_origin_edition_gold_proof_chain.py --require-gold.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output or args.evidence_root / "ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json"
    context = OriginEditionContext.from_env(
        project_id=args.project_id,
        family_name=args.family_name,
        given_name=args.given_name,
        runner_name=args.runner_name,
        namespace=args.namespace,
        base_url=args.base_url,
        require_explicit=True,
    )
    payload = run_chain(
        repo_root=args.repo_root,
        ea_root=args.ea_root,
        evidence_root=args.evidence_root,
        env_file=args.env_file,
        output=output,
        context=context,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] == "pass" or args.allow_blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
