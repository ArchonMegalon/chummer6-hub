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


CONTRACT_NAME = "chummer.origin_edition.runsite_integration_proof.v1"
DEFAULT_EVIDENCE_ROOT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold")


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def env_key_present(path: Path, key: str) -> bool:
    if not path.is_file():
        return False
    prefix = f"{key}="
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return bool(stripped.split("=", 1)[1].strip())
    return False


def contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def check_file_contains(name: str, path: Path, needles: list[str], root: Path) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "path": path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix(),
        "required": True,
    }
    if not path.is_file():
        item["status"] = "missing_file"
        item["missing"] = needles
        return item
    text = read_text(path)
    missing = [needle for needle in needles if needle not in text]
    item["sha256"] = sha256_file(path)
    item["status"] = "pass" if not missing else "missing_expected_content"
    item["missing"] = missing
    return item


def receipt_status(name: str, path: Path, root: Path, expected_status: str = "pass") -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "path": path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix(),
        "required": True,
    }
    if not path.is_file():
        item["status"] = "missing_file"
        return item
    payload = read_json(path)
    item["sha256"] = sha256_file(path)
    item["reportedStatus"] = payload.get("status")
    item["goldEligible"] = payload.get("goldEligible")
    item["status"] = "pass" if str(payload.get("status") or "").lower() == expected_status else "unexpected_status"
    return item


def receipt_summary(name: str, path: Path, root: Path) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "path": path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix(),
        "required": True,
    }
    if not path.is_file():
        item["status"] = "missing_file"
        return item
    payload = read_json(path)
    item["status"] = "present"
    item["sha256"] = sha256_file(path)
    item["contractName"] = payload.get("contractName")
    item["reportedStatus"] = payload.get("status")
    item["goldEligible"] = payload.get("goldEligible")
    item["goalCompletionClaimAllowed"] = payload.get("goalCompletionClaimAllowed")
    item["blockers"] = payload.get("blockers", [])
    item["failedCodes"] = payload.get("failedCodes", [])
    return item


def materialize(
    repo_root: Path,
    ea_root: Path,
    evidence_root: Path,
    output: Path,
    context: OriginEditionContext | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    ea_root = ea_root.resolve()
    evidence_root = evidence_root.resolve()
    context = context or OriginEditionContext.default()
    branch = context.branch(evidence_root)
    checks: list[dict[str, Any]] = []

    checks.append(
        check_file_contains(
            "runsite_handoff_constraints",
            repo_root / "RUNSITE_HANDOFF.md",
            [
                "Before implementing, inspect the newest entries in `LTDs.md` and `.env`.",
                "Do not hardcode secrets from `.env` into committed files.",
                "Wire from env only.",
                "Rybbit",
                "Do not deploy unless explicitly asked.",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "origin_dossier_authenticated_page",
            repo_root / "Chummer.Run.Api/Views/Accounts/OriginDossier.cshtml",
            [
                "data-origin-edition-tabs",
                "href=\"#origin-edition-read\"",
                "href=\"#origin-edition-listen\"",
                "href=\"#origin-edition-watch\"",
                "href=\"#origin-edition-canon-audit\"",
                "Read in Audiobookshelf",
                "Listen in Audiobookshelf",
                "Watch scene movie",
                "Chummer will not publish provider-created facts directly.",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "origin_dossier_private_route_controller",
            repo_root / "Chummer.Run.Api/Controllers/AccountsController.cs",
            [
                "[HttpGet(\"/account/work/origin-dossiers/{originDossierProjectId}\")]",
                "_identity.RequireSubjectAsync",
                "Redirect($\"/login?next={Uri.EscapeDataString(currentPath)}\")",
                "[HttpGet(\"/account/work/origin-dossiers/{originDossierProjectId}/{artifactKind}\")]",
                "PhysicalFile(artifact.Path, artifact.ContentType, enableRangeProcessing: true)",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "origin_publication_gold_gate_service",
            repo_root / "Chummer.Run.Api/Services/Community/OriginDossierPublicationService.cs",
            [
                "Chummer OriginBookEngine",
                "HasFinalNoFallbackNoSentinelReceipt",
                "HasCoverConsistencyReceipt",
                "CHUMMER_ORIGIN_AUDIOBOOKSHELF_TRUSTED_HOSTS",
                "OriginDossier:AudiobookshelfTrustedHosts",
                "FinalNoFallbackNoSentinelAuditReceiptPath",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "rybbit_env_only_layout",
            repo_root / "Chummer.Run.Api/Views/Shared/_Layout.cshtml",
            [
                "RYBBIT_CHUMMER_RUN_SITE_ID",
                "RYBBIT_CHUMMER_RUN_SCRIPT_URL",
                "RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN",
                "RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY",
                "GetEnvironmentVariable",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "runsite_env_example_rybbit",
            repo_root / ".env.example",
            [
                "RYBBIT_CHUMMER_RUN_SITE_ID=",
                "RYBBIT_CHUMMER_RUN_SCRIPT_URL=",
                "RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN=https://app.rybbit.io",
                "RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY=false",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "runsite_compose_rybbit",
            repo_root / "docker-compose.public-edge.yml",
            [
                "RYBBIT_CHUMMER_RUN_SITE_ID: ${RYBBIT_CHUMMER_RUN_SITE_ID:-}",
                "RYBBIT_CHUMMER_RUN_SCRIPT_URL: ${RYBBIT_CHUMMER_RUN_SCRIPT_URL:-}",
                "RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN: ${RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN:-https://app.rybbit.io}",
                "RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY: ${RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY:-false}",
            ],
            repo_root,
        )
    )

    local_env = repo_root / ".env"
    ea_env = ea_root / ".env"
    ltds = ea_root / "LTDs.md"
    ltd_text = read_text(ltds) if ltds.is_file() else ""
    inventory = {
        "runsiteEnvInspected": local_env.is_file(),
        "eaEnvInspected": ea_env.is_file(),
        "ltdInventoryInspected": ltds.is_file(),
        "rybbitRunKeysPresent": {
            key: env_key_present(local_env, key)
            for key in [
                "RYBBIT_CHUMMER_RUN_SITE_ID",
                "RYBBIT_CHUMMER_RUN_SCRIPT_URL",
                "RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN",
                "RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY",
            ]
        },
        "newestProviderInventorySignals": {
            "crezloTours": "Crezlo Tours" in ltd_text and "EA_CREZLO_LOGIN_EMAIL" in read_text(ea_env) if ea_env.is_file() else False,
            "pano2vr": "Pano2VR" in ltd_text and "PANO2VR_LICENSE_KEY" in read_text(ea_env) if ea_env.is_file() else False,
            "unmixr": "Unmixr AI" in ltd_text and env_key_present(ea_env, "UNMIXR_API_KEY"),
            "youbooks": "YouBooks" in ltd_text and "YOUBOOKS_ACCOUNT_EMAILS" in read_text(ea_env) if ea_env.is_file() else False,
            "firstBook": "First Book ai" in ltd_text,
            "inkfluence": env_key_present(local_env, "CHUMMER_EA_INKFLUENCE_BASE_URL"),
        },
    }
    checks.append(
        {
            "name": "newest_ltd_and_env_inputs_inspected",
            "required": True,
            "status": "pass"
            if inventory["runsiteEnvInspected"]
            and inventory["eaEnvInspected"]
            and inventory["ltdInventoryInspected"]
            and all(inventory["rybbitRunKeysPresent"].values())
            and all(inventory["newestProviderInventorySignals"].values())
            else "missing_expected_inventory_signal",
        }
    )

    checks.append(
        receipt_status(
            "live_import_request",
            evidence_root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json",
            evidence_root,
        )
    )
    checks.append(
        receipt_status(
            "local_authenticated_route_proof",
            branch / "authenticated-chummer-route-live.receipt.json",
            evidence_root,
        )
    )
    checks.append(
        receipt_status(
            "final_no_sentinel_media_audit",
            branch / "final-no-fallback-no-sentinel-audit.receipt.json",
            evidence_root,
        )
    )
    deployed_probe = branch / "deployed-chummer-browser-probe.receipt.json"
    deployed_payload = read_json(deployed_probe) if deployed_probe.is_file() else {}
    deployed_handoff = branch / "deployed-operator-handoff.receipt.json"
    gold_audit = evidence_root / "ORIGIN_EDITION_GOLD_CURRENT_GAP_AUDIT.generated.json"
    deployed_status = str(deployed_payload.get("status") or "").lower()
    handoff_summary = receipt_summary("deployed_operator_handoff", deployed_handoff, evidence_root)
    gold_summary = receipt_summary("current_gold_gap_audit", gold_audit, evidence_root)
    gold_evidence_passed = (
        deployed_status == "pass"
        and str(gold_summary.get("reportedStatus") or "").lower() == "pass"
        and gold_summary.get("goalCompletionClaimAllowed") is True
    )
    check_statuses = {str(item.get("name") or ""): item.get("status") for item in checks if isinstance(item, dict)}
    rybbit_env_only = (
        check_statuses.get("rybbit_env_only_layout") == "pass"
        and check_statuses.get("runsite_env_example_rybbit") == "pass"
        and check_statuses.get("runsite_compose_rybbit") == "pass"
    )
    newest_ltds_inspected = (
        inventory["runsiteEnvInspected"]
        and inventory["eaEnvInspected"]
        and inventory["ltdInventoryInspected"]
        and all(inventory["newestProviderInventorySignals"].values())
    )
    env_inspected = inventory["runsiteEnvInspected"] and inventory["eaEnvInspected"]
    runsite_handoff_verified = check_statuses.get("runsite_handoff_constraints") == "pass"
    secret_values_stored = False
    deployment_performed = False

    blocked = [item["name"] for item in checks if item.get("status") != "pass"]
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "status": "pass" if not blocked else "blocked",
        "integrationEligible": not blocked,
        "goldEligible": not blocked and gold_evidence_passed,
        "goalCompletionClaimAllowed": False,
        "namespace": context.resolved_namespace,
        "projectId": context.project_id,
        "runsiteHandoffVerified": runsite_handoff_verified,
        "newestLtdsInspected": newest_ltds_inspected,
        "envInspected": env_inspected,
        "rybbitEnvOnly": rybbit_env_only,
        "deploymentPerformed": deployment_performed,
        "secretValuesStored": secret_values_stored,
        "checks": checks,
        "blockedChecks": blocked,
        "inventoryInspection": inventory,
        "deployedBrowserProbe": {
            "path": deployed_probe.relative_to(evidence_root).as_posix(),
            "status": deployed_payload.get("status"),
            "deployedRouteClaimAllowed": deployed_payload.get("deployedRouteClaimAllowed"),
            "blockers": deployed_payload.get("blockers", []),
            "sha256": sha256_file(deployed_probe) if deployed_probe.is_file() else "",
        },
        "deployedOperatorHandoff": handoff_summary,
        "currentGoldGapAudit": gold_summary,
        "privacy": {
            "envValuesExposed": False,
            "rawCredentialExposed": False,
            "rawSessionTokenExposed": False,
            "deploymentPerformed": deployment_performed,
        },
        "claim": "RunSite integration is wired and locally proven; final Gold still requires a deployed owner-session browser proof.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Origin Edition RunSite integration proof without exposing secrets.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ea-root", type=Path, default=Path("/docker/EA"))
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
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
    )
    output = args.output or context.branch(args.evidence_root) / "runsite-integration-proof.receipt.json"
    payload = materialize(args.repo_root, args.ea_root, args.evidence_root, output, context)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
