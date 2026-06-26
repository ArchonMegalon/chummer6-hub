from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_dossier_portal_restart_plan.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_dossier_portal_restart_plan", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_compose(path: Path) -> None:
    path.write_text(
        "services:\n"
        "  chummer-portal:\n"
        "    environment:\n"
        "      CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX: ${CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX:-/app/state/origin-dossier-publications.json}\n",
        encoding="utf-8",
    )


def test_restart_plan_waits_for_explicit_approval_without_deploying(tmp_path: Path) -> None:
    module = load_module()
    branch = Path("origin.chummer.run/Varga/Mira/Kestrel")
    preflight = tmp_path / branch / "portal-publication-index-preflight.receipt.json"
    write_json(
        preflight,
        {
            "status": "blocked",
            "restartRequiredForExistingContainer": True,
        },
    )
    compose = tmp_path / "docker-compose.public-edge.yml"
    write_compose(compose)

    output = tmp_path / branch / "portal-restart-plan.receipt.json"
    result = module.materialize(output, evidence_root=tmp_path, branch=branch, compose_file=compose)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "awaiting_explicit_restart_approval"
    assert result["safeToExecuteAfterApproval"] is True
    assert result["deploymentPerformed"] is False
    assert result["approvalGate"] == "explicit_user_deploy_or_restart_approval_required"
    assert "docker compose -f docker-compose.public-edge.yml up -d --no-deps --force-recreate chummer-portal" in result["restartCommands"]
    assert "materialize_origin_dossier_deployed_browser_probe.py" in serialized
    assert result["privacy"]["rawCredentialExposed"] is False
    assert result["privacy"]["rawEnvValueExposed"] is False


def test_restart_plan_blocks_without_preflight_restart_requirement(tmp_path: Path) -> None:
    module = load_module()
    branch = Path("origin.chummer.run/Varga/Mira/Kestrel")
    preflight = tmp_path / branch / "portal-publication-index-preflight.receipt.json"
    write_json(
        preflight,
        {
            "status": "pass",
            "restartRequiredForExistingContainer": False,
        },
    )
    compose = tmp_path / "docker-compose.public-edge.yml"
    write_compose(compose)

    result = module.materialize(
        tmp_path / branch / "portal-restart-plan.receipt.json",
        evidence_root=tmp_path,
        branch=branch,
        compose_file=compose,
    )

    assert result["status"] == "blocked"
    assert result["safeToExecuteAfterApproval"] is False
    assert "portal_preflight_restart_required_not_true" in result["blockers"]
    assert result["deploymentPerformed"] is False
