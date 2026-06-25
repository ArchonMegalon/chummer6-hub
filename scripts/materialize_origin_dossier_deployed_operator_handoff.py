#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_context import OriginEditionContext


DEFAULT_EVIDENCE_ROOT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold")
E2E_ENV_KEYS = {
    "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN",
    "CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN",
    "CHUMMER_DEPLOYED_E2E_AUTH_MODE",
    "CHUMMER_DEPLOYED_E2E_COOKIE_NAME",
    "CHUMMER_DEPLOYED_E2E_COOKIE_HEADER",
    "CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER",
}
REQUIRED_DEPLOYED_PROBE_FLAGS = (
    "logged_in_browser_verified",
    "selected_face_cover_marker_visible",
    "selected_face_cover_alt_visible",
    "selected_face_cover_route_visible",
    "selected_face_cover_visible",
    "read_tab_visible",
    "read_section_visible",
    "listen_tab_visible",
    "listen_section_visible",
    "watch_tab_visible",
    "watch_section_visible",
    "canon_audit_tab_visible",
    "canon_audit_section_visible",
    "chummer_canon_owner_visible",
    "provider_created_facts_blocked_visible",
    "canon_privacy_receipts_present",
    "no_fallback_media_verified",
    "canon_audit_content_verified",
    "read_gate_verified",
    "chummer_run_listen_gate_verified",
    "watch_gate_verified",
    "cover_route_verified",
    "book_route_verified",
    "watch_artifact_nonempty",
    "cover_artifact_nonempty",
    "book_artifact_nonempty",
    "cover_sha_matches_import",
    "book_sha_matches_import",
    "video_sha_matches_import",
    "audiobook_share_url_trusted",
    "dossier_share_url_trusted",
    "audiobook_share_reachable",
    "dossier_share_reachable",
    "owner_playback_e2e_verified",
    "unauthenticated_detail_redirect_verified",
    "unauthenticated_read_redirect_verified",
    "unauthenticated_listen_redirect_verified",
    "unauthenticated_book_redirect_verified",
    "unauthenticated_cover_redirect_verified",
    "unauthenticated_video_redirect_verified",
    "all_private_routes_login_protected",
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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


def load_env_file(path: Path | None) -> dict[str, bool]:
    loaded: dict[str, bool] = {}
    if path is None or not path.is_file():
        return loaded
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if key not in E2E_ENV_KEYS or os.environ.get(key):
            continue
        value = raw_value.strip().strip('"').strip("'")
        if value:
            os.environ[key] = value
            loaded[key] = True
        else:
            loaded[key] = False
    return loaded


OWNER_SESSION_ENV_KEYS = (
    "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN",
    "CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN",
    "CHUMMER_DEPLOYED_E2E_COOKIE_HEADER",
    "CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER",
)


def owner_session_present() -> bool:
    return any(os.environ.get(key, "").strip() for key in OWNER_SESSION_ENV_KEYS)


def quote(value: object) -> str:
    return shlex.quote(str(value))


def context_args(context: OriginEditionContext) -> str:
    return " ".join(
        [
            f"--project-id {quote(context.project_id)}",
            f"--family-name {quote(context.family_name)}",
            f"--given-name {quote(context.given_name)}",
            f"--runner-name {quote(context.runner_name)}",
            f"--namespace {quote(context.resolved_namespace)}",
            f"--base-url {quote(context.base_url)}",
        ]
    )


def materialize(
    evidence_root: Path,
    output: Path,
    env_file: Path | None = None,
    context: OriginEditionContext | None = None,
) -> dict[str, Any]:
    evidence_root = evidence_root.resolve()
    context = context or OriginEditionContext.from_env(require_explicit=True)
    branch = context.branch(evidence_root)
    loaded_env = load_env_file(env_file)
    deployed_probe = branch / "deployed-chummer-browser-probe.receipt.json"
    gold_audit = evidence_root / "ORIGIN_EDITION_GOLD_CURRENT_GAP_AUDIT.generated.json"
    runsite_proof = branch / "runsite-integration-proof.receipt.json"
    live_import = evidence_root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    evidence_root_text = evidence_root.as_posix()
    branch_text = branch.as_posix()

    deployed_payload = read_json(deployed_probe) if deployed_probe.is_file() else {}
    gold_payload = read_json(gold_audit) if gold_audit.is_file() else {}
    deployed_flag_status = {
        flag: deployed_payload.get(flag) is True
        for flag in REQUIRED_DEPLOYED_PROBE_FLAGS
    }
    missing_deployed_flags = [flag for flag, passed in deployed_flag_status.items() if not passed]
    origin_context_args = context_args(context)
    required_commands = [
        "Set exactly one deployed owner-session input in /docker/chummercomplete/chummer.run-services/.env or in the current process: CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN, CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN, CHUMMER_DEPLOYED_E2E_COOKIE_HEADER, or CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER.",
        f"python3 scripts/materialize_origin_dossier_deployed_browser_probe.py --env-file /docker/chummercomplete/chummer.run-services/.env --evidence-root {quote(evidence_root_text)} {origin_context_args}",
        f"python3 scripts/audit_origin_dossier_gold_e2e.py --live-import-request {evidence_root_text}/ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json --ea-delivery-receipt {branch_text}/telegram-origin-link-bundle-live.receipt.json --browser-proof {branch_text}/deployed-chummer-browser-probe.receipt.json --deployed-operator-handoff {branch_text}/deployed-operator-handoff.receipt.json --output {evidence_root_text}/ORIGIN_EDITION_GOLD_CURRENT_GAP_AUDIT.generated.json --pretty --require-pass",
        f"python3 scripts/materialize_origin_edition_gold_proof_chain.py --env-file /docker/chummercomplete/chummer.run-services/.env --evidence-root {quote(evidence_root_text)} {origin_context_args} --allow-blocked",
        f"python3 scripts/materialize_origin_edition_gold_final_verdict.py --evidence-root {quote(evidence_root_text)} {origin_context_args} --allow-blocked",
        f"python3 scripts/verify_origin_edition_gold_proof_chain.py --proof-chain {evidence_root_text}/ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json --require-gold",
        f"python3 scripts/verify_origin_edition_gold_final_verdict.py --verdict {evidence_root_text}/FINAL_ORIGIN_EDITION_GOLD_VERDICT.md --proof-chain {evidence_root_text}/ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json --requirement-coverage {evidence_root_text}/ORIGIN_EDITION_GOLD_REQUIREMENT_COVERAGE.generated.json",
        "CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD=1 bash scripts/ai/run_services_verification.sh",
    ]
    blockers = []
    if not owner_session_present():
        blockers.append("missing_deployed_owner_session")
    if deployed_payload.get("status") != "pass":
        blockers.append("deployed_browser_probe_not_pass")
    blockers.extend(f"deployed_browser_probe_flag_missing:{flag}" for flag in missing_deployed_flags)
    if gold_payload.get("status") != "pass":
        blockers.append("gold_audit_not_pass")
    ready_for_operator_token = (
        not owner_session_present()
        and "deployed_browser_probe_not_pass" in blockers
        and "gold_audit_not_pass" in blockers
    )
    status = "ready_for_operator_token" if ready_for_operator_token else ("pass" if not blockers else "blocked")
    deployed_progress = deployed_payload.get("progress") if isinstance(deployed_payload.get("progress"), dict) else {}
    next_action = (
        str(deployed_payload.get("next_action") or "").strip()
        or "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN for a real deployed owner session and rerun this probe."
        if status == "ready_for_operator_token"
        else "Resolve deployed Origin Edition blockers and rerun the strict Gold proof chain."
    )
    blocking_reason = "" if status == "pass" else ",".join(blockers)
    progress = {
        "deployedProbe": deployed_progress,
        "missingDeployedFlags": missing_deployed_flags,
        "blockerCount": len(blockers),
    }

    payload: dict[str, Any] = {
        "contractName": "chummer.origin_edition.deployed_operator_handoff.v1",
        "generatedAtUtc": now_iso(),
        "updated_at": now_iso(),
        "status": status,
        "goldEligible": False,
        "goalCompletionClaimAllowed": False,
        "next_action": next_action,
        "blocking_reason": blocking_reason,
        "progress": progress,
        "namespace": context.resolved_namespace,
        "projectId": context.project_id,
        "context": {
            "projectId": context.project_id,
            "familyName": context.family_name,
            "givenName": context.given_name,
            "runnerName": context.runner_name,
            "namespace": context.resolved_namespace,
            "baseUrl": context.base_url,
        },
        "deployedOwnerUrl": context.owner_url,
        "requiredEnv": {
            "CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD": {
                "requiredForRelease": True,
                "expectedValueForRelease": "1",
                "valueStoredInReceipt": False,
                "operatorInstruction": "Set to 1 only for release/gold verification so a blocked deployed proof cannot pass CI.",
            },
            "deployedOwnerSession": {
                "required": True,
                "acceptedKeys": list(OWNER_SESSION_ENV_KEYS),
                "presentInCurrentProcess": owner_session_present(),
                "valueStoredInReceipt": False,
                "operatorInstruction": "Use one short-lived real owner session input only for the probe process; do not commit or paste it into artifacts.",
            }
        },
        "envFile": {
            "provided": env_file is not None,
            "pathSha256": hashlib.sha256(env_file.as_posix().encode("utf-8")).hexdigest() if env_file is not None else "",
            "loadedKeys": sorted(loaded_env.keys()),
            "valuesStoredInReceipt": False,
        },
        "requiredCommands": required_commands,
        "currentEvidence": {
            "liveImportRequestSha256": sha256_file(live_import) if live_import.is_file() else "",
            "runsiteIntegrationProofSha256": sha256_file(runsite_proof) if runsite_proof.is_file() else "",
            "deployedProbeSha256": sha256_file(deployed_probe) if deployed_probe.is_file() else "",
            "goldAuditSha256": sha256_file(gold_audit) if gold_audit.is_file() else "",
            "deployedProbeStatus": deployed_payload.get("status"),
            "deployedProbeNextAction": deployed_payload.get("next_action"),
            "deployedProbeBlockingReason": deployed_payload.get("blocking_reason"),
            "deployedProbeProgress": deployed_progress,
            "goldAuditStatus": gold_payload.get("status"),
            "deployedProbeBlockers": deployed_payload.get("blockers", []),
            "deployedProbeRequiredFlags": deployed_flag_status,
            "deployedProbeMissingRequiredFlags": missing_deployed_flags,
            "goldAuditFailedCodes": gold_payload.get("failedCodes", []),
        },
        "blockers": blockers,
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
    parser = argparse.ArgumentParser(description="Materialize secret-safe deployed Origin Dossier operator handoff.")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--env-file", type=Path, help="Optional local env file containing CHUMMER_DEPLOYED_E2E_* values.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--family-name")
    parser.add_argument("--given-name")
    parser.add_argument("--runner-name")
    parser.add_argument("--namespace")
    parser.add_argument("--base-url")
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
    output = args.output or context.branch(args.evidence_root) / "deployed-operator-handoff.receipt.json"
    payload = materialize(args.evidence_root, output, args.env_file, context)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("status") in {"pass", "ready_for_operator_token"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
