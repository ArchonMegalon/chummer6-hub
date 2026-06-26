#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shlex
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_context import OriginEditionContext


CONTRACT_NAME = "chummer.origin_edition.portal_restart_plan.v1"
DEFAULT_EVIDENCE_ROOT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold")
DEFAULT_EXPECTED_INDEX = "/app/state/origin-dossier-publications.json"
DEFAULT_HOST_STATE_ROOT = Path("/var/lib/docker/volumes/chummer6-hub_chummer-run-api-state/_data")


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_text(value: object) -> str:
    text = str(value or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def compose_has_index(path: Path, expected_index: str) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    return "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX" in text and expected_index in text


def shell_join(parts: list[object]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts if str(part).strip())


def build_restart_commands(
    *,
    evidence_root: Path,
    branch_path: Path,
    compose_file: Path,
    host_state_root: Path,
    env_file: Path | None,
    context: OriginEditionContext,
) -> list[str]:
    probe_command: list[object] = [
        "python3",
        "scripts/materialize_origin_dossier_deployed_browser_probe.py",
    ]
    if env_file is not None:
        probe_command.extend(["--env-file", env_file])
    probe_command.extend(
        [
            "--evidence-root",
            evidence_root,
            "--project-id",
            context.project_id,
            "--family-name",
            context.family_name,
            "--given-name",
            context.given_name,
            "--runner-name",
            context.runner_name,
            "--namespace",
            context.resolved_namespace,
            "--base-url",
            context.base_url,
        ]
    )
    return [
        shell_join([
            "docker",
            "compose",
            "-f",
            compose_file,
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            "chummer-portal",
        ]),
        shell_join([
            "python3",
            "scripts/materialize_origin_dossier_portal_publication_index_preflight.py",
            "--output",
            branch_path / "portal-publication-index-preflight.receipt.json",
            "--host-state-root",
            host_state_root,
        ]),
        shell_join(probe_command),
    ]


def materialize(
    output: Path,
    *,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    branch: Path | None = None,
    expected_index: str = DEFAULT_EXPECTED_INDEX,
    compose_file: Path = Path("docker-compose.public-edge.yml"),
    host_state_root: Path = DEFAULT_HOST_STATE_ROOT,
    env_file: Path | None = Path("/docker/chummercomplete/chummer.run-services/.env"),
    preflight: Path | None = None,
    context: OriginEditionContext | None = None,
) -> dict[str, Any]:
    evidence_root = evidence_root.resolve()
    context = context or OriginEditionContext.from_env()
    resolved_branch = branch or Path(context.resolved_namespace)
    branch_path = evidence_root / resolved_branch
    preflight_path = preflight or branch_path / "portal-publication-index-preflight.receipt.json"
    preflight_payload = read_json(preflight_path) if preflight_path.is_file() else {}
    preflight_status = str(preflight_payload.get("status") or "")
    restart_required = preflight_payload.get("restartRequiredForExistingContainer") is True
    restart_not_required = preflight_status == "pass" and preflight_payload.get("restartRequiredForExistingContainer") is False
    compose_configured = compose_has_index(compose_file, expected_index)
    safe_after_approval = restart_required and compose_configured
    blockers: list[str] = []
    if not preflight_path.is_file():
        blockers.append("portal_publication_index_preflight_missing")
    if not restart_not_required and preflight_status != "blocked":
        blockers.append("portal_preflight_not_in_restart_required_blocked_state")
    if not restart_not_required and not restart_required:
        blockers.append("portal_preflight_restart_required_not_true")
    if not compose_configured:
        blockers.append("compose_publication_index_env_missing")
    status = "not_required" if restart_not_required else "awaiting_explicit_restart_approval" if safe_after_approval else "blocked"
    commands = build_restart_commands(
        evidence_root=evidence_root,
        branch_path=branch_path,
        compose_file=compose_file,
        host_state_root=host_state_root,
        env_file=env_file,
        context=context,
    )
    payload = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "updated_at": now_iso(),
        "status": status,
        "goalCompletionClaimAllowed": False,
        "deploymentPerformed": False,
        "approvalGate": "explicit_user_deploy_or_restart_approval_required" if status == "awaiting_explicit_restart_approval" else "",
        "safeToExecuteAfterApproval": safe_after_approval,
        "expectedContainerPublicationIndex": expected_index,
        "originEditionContext": {
            "projectId": context.project_id,
            "familyName": context.family_name,
            "givenName": context.given_name,
            "runnerName": context.runner_name,
            "namespace": context.resolved_namespace,
            "baseUrl": context.base_url,
        },
        "preflight": {
            "present": preflight_path.is_file(),
            "pathSha256": sha256_text(preflight_path.as_posix()),
            "sha256": sha256_file(preflight_path) if preflight_path.is_file() else "",
            "status": preflight_status,
            "restartRequiredForExistingContainer": restart_required,
        },
        "compose": {
            "present": compose_file.is_file(),
            "pathSha256": sha256_text(compose_file.as_posix()),
            "publicationIndexConfigured": compose_configured,
        },
        "restartCommands": commands,
        "postRestartVerificationRequired": status == "awaiting_explicit_restart_approval",
        "postRestartRequiredEvidence": [
            "portal_publication_index_preflight_status_pass",
            "deployed_browser_probe_status_pass",
            "origin_gold_proof_chain_status_pass",
            "final_verdict_gold_ready",
        ],
        "next_action": "Portal publication index is already active; restart is not required." if status == "not_required" else "Await explicit deploy/restart approval, then run restartCommands exactly once and rerun strict Gold verification." if status == "awaiting_explicit_restart_approval" else "Resolve restart-plan blockers before requesting restart approval.",
        "blocking_reason": "" if status in {"not_required", "awaiting_explicit_restart_approval"} else ",".join(blockers),
        "blockers": blockers,
        "privacy": {"rawCredentialExposed": False, "rawEnvValueExposed": False, "deploymentPerformed": False},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize a non-destructive Origin Dossier portal restart plan.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--branch", type=Path)
    parser.add_argument("--expected-index", default=DEFAULT_EXPECTED_INDEX)
    parser.add_argument("--compose-file", type=Path, default=Path("docker-compose.public-edge.yml"))
    parser.add_argument("--host-state-root", type=Path, default=DEFAULT_HOST_STATE_ROOT)
    parser.add_argument("--env-file", type=Path, default=Path("/docker/chummercomplete/chummer.run-services/.env"))
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--family-name")
    parser.add_argument("--given-name")
    parser.add_argument("--runner-name")
    parser.add_argument("--namespace")
    parser.add_argument("--base-url")
    args = parser.parse_args()
    context = OriginEditionContext.from_env(
        project_id=args.project_id,
        family_name=args.family_name,
        given_name=args.given_name,
        runner_name=args.runner_name,
        namespace=args.namespace,
        base_url=args.base_url,
    )
    branch = args.branch or Path(context.resolved_namespace)
    output = args.output or args.evidence_root / branch / "portal-restart-plan.receipt.json"
    payload = materialize(
        output,
        evidence_root=args.evidence_root,
        branch=branch,
        expected_index=args.expected_index,
        compose_file=args.compose_file,
        host_state_root=args.host_state_root,
        env_file=args.env_file,
        preflight=args.preflight,
        context=context,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] in {"awaiting_explicit_restart_approval", "not_required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
