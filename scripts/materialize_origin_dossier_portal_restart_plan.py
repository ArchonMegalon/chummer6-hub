#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any


CONTRACT_NAME = "chummer.origin_edition.portal_restart_plan.v1"
DEFAULT_EVIDENCE_ROOT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold")
DEFAULT_BRANCH = Path("origin.chummer.run/Varga/Mira/Kestrel")
DEFAULT_EXPECTED_INDEX = "/app/state/origin-dossier-publications.json"


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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def compose_has_index(compose_file: Path, expected_index: str) -> bool:
    text = read_text(compose_file)
    return "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX" in text and expected_index in text


def materialize(
    output: Path,
    *,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    branch: Path = DEFAULT_BRANCH,
    expected_index: str = DEFAULT_EXPECTED_INDEX,
    compose_file: Path = Path("docker-compose.public-edge.yml"),
    preflight: Path | None = None,
) -> dict[str, Any]:
    evidence_root = evidence_root.resolve()
    branch_path = evidence_root / branch
    preflight_path = preflight or branch_path / "portal-publication-index-preflight.receipt.json"
    preflight_payload = read_json(preflight_path) if preflight_path.is_file() else {}
    preflight_restart_required = preflight_payload.get("restartRequiredForExistingContainer") is True
    preflight_status = str(preflight_payload.get("status") or "")
    compose_configured = compose_has_index(compose_file, expected_index)
    restart_not_required = preflight_path.is_file() and preflight_status == "pass" and not preflight_restart_required
    safe_to_prepare = preflight_restart_required and compose_configured
    blockers: list[str] = []
    if not restart_not_required:
        if not preflight_path.is_file():
            blockers.append("portal_publication_index_preflight_missing")
        if preflight_status != "blocked":
            blockers.append("portal_preflight_not_in_restart_required_blocked_state")
        if not preflight_restart_required:
            blockers.append("portal_preflight_restart_required_not_true")
        if not compose_configured:
            blockers.append("compose_publication_index_env_missing")

    approval_gate = "explicit_user_deploy_or_restart_approval_required"
    local_status_receipt = branch_path / "public-edge-downloads-version-marker.receipt.json"
    restart_commands = [
        'CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD="$(git rev-parse HEAD)" CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM=1 '
        "bash scripts/deploy_public_edge_portal.sh",
        "python3 scripts/verify_downloads_version_marker.py --base-url http://127.0.0.1:8091 --output "
        f"{local_status_receipt.as_posix()}",
        "python3 scripts/materialize_origin_dossier_portal_publication_index_preflight.py --output "
        f"{(branch_path / 'portal-publication-index-preflight.receipt.json').as_posix()} "
        "--host-state-root /var/lib/docker/volumes/chummer6-hub_chummer-run-api-state/_data",
        "python3 scripts/materialize_origin_dossier_deployed_browser_probe.py --env-file "
        "/docker/chummercomplete/chummer.run-services/.env --evidence-root "
        f"{evidence_root.as_posix()} --project-id varga-mira-kestrel --family-name Varga "
        "--given-name Mira --runner-name Kestrel --namespace origin.chummer.run/Varga/Mira/Kestrel "
        "--base-url https://chummer.run",
    ]
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "updated_at": now_iso(),
        "status": "not_required" if restart_not_required else "awaiting_explicit_restart_approval" if safe_to_prepare else "blocked",
        "goalCompletionClaimAllowed": False,
        "deploymentPerformed": False,
        "approvalGate": "" if restart_not_required else approval_gate,
        "safeToExecuteAfterApproval": safe_to_prepare,
        "expectedContainerPublicationIndex": expected_index,
        "preflight": {
            "pathSha256": sha256_text(preflight_path.as_posix()),
            "present": preflight_path.is_file(),
            "sha256": sha256_file(preflight_path) if preflight_path.is_file() else "",
            "status": preflight_status,
            "restartRequiredForExistingContainer": preflight_restart_required,
        },
        "compose": {
            "pathSha256": sha256_text(compose_file.as_posix()),
            "present": compose_file.is_file(),
            "publicationIndexConfigured": compose_configured,
        },
        "restartCommands": restart_commands,
        "postRestartVerificationRequired": not restart_not_required,
        "postRestartRequiredEvidence": [
            "local_public_edge_downloads_version_marker_status_pass",
            "portal_publication_index_preflight_status_pass",
            "deployed_browser_probe_status_pass",
            "origin_gold_proof_chain_status_pass",
            "final_verdict_gold_ready",
        ],
        "next_action": (
            "Restart not required; portal publication index is already active in the running container."
            if restart_not_required
            else "Await explicit deploy/restart approval, then run restartCommands exactly once and rerun strict Gold verification."
            if safe_to_prepare
            else "Resolve restart-plan blockers before requesting restart approval."
        ),
        "blocking_reason": "" if restart_not_required or safe_to_prepare else ",".join(blockers),
        "blockers": blockers,
        "privacy": {
            "rawCredentialExposed": False,
            "rawEnvValueExposed": False,
            "deploymentPerformed": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize a non-destructive Origin Dossier portal restart plan.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--branch", type=Path, default=DEFAULT_BRANCH)
    parser.add_argument("--expected-index", default=DEFAULT_EXPECTED_INDEX)
    parser.add_argument("--compose-file", type=Path, default=Path("docker-compose.public-edge.yml"))
    parser.add_argument("--preflight", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output or args.evidence_root / args.branch / "portal-restart-plan.receipt.json"
    payload = materialize(
        output,
        evidence_root=args.evidence_root,
        branch=args.branch,
        expected_index=args.expected_index,
        compose_file=args.compose_file,
        preflight=args.preflight,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("status") == "awaiting_explicit_restart_approval" else 1


if __name__ == "__main__":
    raise SystemExit(main())
