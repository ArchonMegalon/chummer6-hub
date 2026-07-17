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
    assert result["restartCommands"][0] == (
        'CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD="$(git rev-parse HEAD)" CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM=1 '
        "bash scripts/deploy_public_edge_portal.sh"
    )
    assert not any("docker compose" in command for command in result["restartCommands"])
    assert any("verify_downloads_version_marker.py --base-url http://127.0.0.1:8091 --output " in command for command in result["restartCommands"])
    assert "local_public_edge_downloads_version_marker_status_pass" in result["postRestartRequiredEvidence"]
    assert "materialize_origin_dossier_deployed_browser_probe.py" in serialized
    assert result["privacy"]["rawCredentialExposed"] is False
    assert result["privacy"]["rawEnvValueExposed"] is False


def test_restart_plan_is_not_required_when_preflight_already_passes(tmp_path: Path) -> None:
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

    assert result["status"] == "not_required"
    assert result["safeToExecuteAfterApproval"] is False
    assert result["postRestartVerificationRequired"] is False
    assert result["approvalGate"] == ""
    assert result["blockers"] == []
    assert result["blocking_reason"] == ""
    assert result["deploymentPerformed"] is False
    assert "local_public_edge_downloads_version_marker_status_pass" in result["postRestartRequiredEvidence"]
