#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_context import OriginEditionContext


DEFAULT_EVIDENCE_ROOT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold")
DEFAULT_VERDICT_NAME = "FINAL_ORIGIN_EDITION_GOLD_VERDICT.md"
READY_VERDICT = "ORIGIN_EDITION_GOLD_READY"
BLOCKED_VERDICT = "ORIGIN_EDITION_GOLD_BLOCKED"


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bool_text(value: object) -> str:
    return "true" if value is True else "false"


def stage_lines(proof_chain: dict[str, Any]) -> list[str]:
    stages = proof_chain.get("stages") if isinstance(proof_chain.get("stages"), list) else []
    lines: list[str] = []
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        name = str(stage.get("name") or "unknown_stage")
        status = str(stage.get("status") or "unknown")
        blockers = stage.get("blockers")
        blocked_rows = stage.get("blockedRows")
        blocked_gates = stage.get("blockedHardGates")
        blocked_requirements = stage.get("blockedRequirements")
        suffixes: list[str] = []
        if blockers:
            suffixes.append(f"blockers={json.dumps(blockers, sort_keys=True)}")
        if blocked_rows:
            suffixes.append(f"blockedRows={json.dumps(blocked_rows, sort_keys=True)}")
        if blocked_gates:
            suffixes.append(f"blockedHardGates={json.dumps(blocked_gates, sort_keys=True)}")
        if blocked_requirements:
            suffixes.append(f"blockedRequirements={json.dumps(blocked_requirements, sort_keys=True)}")
        detail = f" ({'; '.join(suffixes)})" if suffixes else ""
        lines.append(f"- `{name}`: `{status}`{detail}")
    return lines or ["- No proof-chain stages were recorded."]


def requirement_lines(coverage: dict[str, Any]) -> list[str]:
    requirements = coverage.get("requirements") if isinstance(coverage.get("requirements"), list) else []
    lines: list[str] = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        rid = str(requirement.get("id") or "unknown_requirement")
        status = str(requirement.get("status") or "unknown")
        label = str(requirement.get("label") or "").strip()
        label_suffix = f" - {label}" if label else ""
        lines.append(f"- `{rid}`: `{status}`{label_suffix}")
    return lines or ["- No requirement coverage rows were recorded."]


def blocked_requirement_lines(blocked: list[str]) -> list[str]:
    if not blocked:
        return ["- None."]
    return [f"- `{item}`" for item in blocked]


def progress_lines(proof_chain: dict[str, Any]) -> list[str]:
    progress = proof_chain.get("progress") if isinstance(proof_chain.get("progress"), dict) else {}
    if not progress:
        return ["- No proof-chain progress summary was recorded."]
    return [
        f"- Passed stages: `{progress.get('passedStages')}` / `{progress.get('totalStages')}`",
        f"- Blocked stages: `{json.dumps(progress.get('blockedStages', []), sort_keys=True)}`",
        f"- Blocking reason: `{proof_chain.get('blocking_reason') or ''}`",
    ]


def materialize(evidence_root: Path, output: Path, context: OriginEditionContext | None = None) -> dict[str, Any]:
    evidence_root = evidence_root.resolve()
    context = context or OriginEditionContext.from_env(require_explicit=True)
    proof_chain_path = evidence_root / "ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json"
    coverage_path = evidence_root / "ORIGIN_EDITION_GOLD_REQUIREMENT_COVERAGE.generated.json"
    proof_chain = read_json(proof_chain_path)
    coverage = read_json(coverage_path)

    blocked_requirements = coverage.get("blockedRequirements")
    if not isinstance(blocked_requirements, list):
        blocked_requirements = []
    blocked_requirements = [str(item) for item in blocked_requirements]

    proof_ready = proof_chain.get("status") == "pass" and proof_chain.get("goalCompletionClaimAllowed") is True
    coverage_ready = coverage.get("status") == "pass" and coverage.get("goalCompletionClaimAllowed") is True
    ready = proof_ready and coverage_ready and not blocked_requirements
    verdict = READY_VERDICT if ready else BLOCKED_VERDICT

    privacy = proof_chain.get("privacy") if isinstance(proof_chain.get("privacy"), dict) else {}
    privacy_lines = [
        f"- `rawCredentialExposed`: `{bool_text(privacy.get('rawCredentialExposed'))}`",
        f"- `rawSessionTokenExposed`: `{bool_text(privacy.get('rawSessionTokenExposed'))}`",
        f"- `envValuesExposed`: `{bool_text(privacy.get('envValuesExposed'))}`",
        f"- `deploymentPerformed`: `{bool_text(privacy.get('deploymentPerformed'))}`",
    ]

    next_action = (
        str(proof_chain.get("next_action") or "").strip()
        or "Set a short-lived real owner session token in the local operator environment, rerun the deployed browser proof "
        "chain, then rerun the strict Gold verifier. Do not claim completion until the owner can read, listen, watch, "
        "and review Canon Audit behind login."
        if not ready
        else "Gold proof chain is ready for release handoff. Keep the artifacts archived outside providers."
    )

    lines = [
        "# Origin Edition Gold Verdict",
        "",
        f"Generated UTC: `{now_iso()}`",
        f"Namespace: `{proof_chain.get('namespace') or context.resolved_namespace}`",
        f"Project ID: `{proof_chain.get('projectId') or context.project_id}`",
        f"Verdict: `{verdict}`",
        f"Goal completion claim allowed: `{bool_text(ready)}`",
        "",
        "## Required Next Action",
        "",
        next_action,
        "",
        "## Blocked Requirements",
        "",
        *blocked_requirement_lines(blocked_requirements),
        "",
        "## Proof Progress",
        "",
        *progress_lines(proof_chain),
        "",
        "## Proof Chain Stages",
        "",
        *stage_lines(proof_chain),
        "",
        "## Requirement Coverage",
        "",
        *requirement_lines(coverage),
        "",
        "## Privacy And Release Boundary",
        "",
        *privacy_lines,
        "",
        "## Source Artifacts",
        "",
        f"- Proof chain: `{proof_chain_path.as_posix()}`",
        f"- Proof chain SHA-256: `{sha256_file(proof_chain_path)}`",
        f"- Requirement coverage: `{coverage_path.as_posix()}`",
        f"- Requirement coverage SHA-256: `{sha256_file(coverage_path)}`",
        "",
    ]

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return {
        "status": "pass" if ready else "blocked",
        "finalVerdict": verdict,
        "goalCompletionClaimAllowed": ready,
        "blockedRequirements": blocked_requirements,
        "nextAction": next_action,
        "output": output.as_posix(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize the operator-readable Origin Edition Gold final verdict.")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
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
        help="Exit zero after writing an honest blocked verdict.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    context = OriginEditionContext.from_env(
        project_id=args.project_id,
        family_name=args.family_name,
        given_name=args.given_name,
        runner_name=args.runner_name,
        namespace=args.namespace,
        base_url=args.base_url,
        require_explicit=True,
    )
    output = args.output or args.evidence_root / DEFAULT_VERDICT_NAME
    payload = materialize(args.evidence_root, output, context)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] == "pass" or args.allow_blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
