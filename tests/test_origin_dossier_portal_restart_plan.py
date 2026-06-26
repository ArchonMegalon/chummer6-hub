from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_dossier_portal_restart_plan.py"


def load_module():
    spec = importlib.util.spec_from_file_location("portal_restart_plan", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_compose(path: Path) -> None:
    path.write_text("CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=/app/state/origin-dossier-publications.json", encoding="utf-8")


def test_restart_plan_waits_for_explicit_approval_without_deploying(tmp_path: Path) -> None:
    module = load_module()
    branch = Path("origin.chummer.run/Varga/Mira/Kestrel")
    write_json(tmp_path / branch / "portal-publication-index-preflight.receipt.json", {"status": "blocked", "restartRequiredForExistingContainer": True})
    compose = tmp_path / "docker-compose.public-edge.yml"
    write_compose(compose)

    result = module.materialize(tmp_path / branch / "portal-restart-plan.receipt.json", evidence_root=tmp_path, branch=branch, compose_file=compose)

    assert result["status"] == "awaiting_explicit_restart_approval"
    assert result["safeToExecuteAfterApproval"] is True
    assert result["deploymentPerformed"] is False
    assert result["approvalGate"] == "explicit_user_deploy_or_restart_approval_required"


def test_restart_plan_is_not_required_after_preflight_passes(tmp_path: Path) -> None:
    module = load_module()
    branch = Path("origin.chummer.run/Varga/Mira/Kestrel")
    write_json(tmp_path / branch / "portal-publication-index-preflight.receipt.json", {"status": "pass", "restartRequiredForExistingContainer": False})
    compose = tmp_path / "docker-compose.public-edge.yml"
    write_compose(compose)

    result = module.materialize(tmp_path / branch / "portal-restart-plan.receipt.json", evidence_root=tmp_path, branch=branch, compose_file=compose)

    assert result["status"] == "not_required"
    assert result["blockers"] == []
    assert result["deploymentPerformed"] is False


def test_restart_plan_uses_explicit_origin_context_instead_of_kestrel_defaults(tmp_path: Path) -> None:
    module = load_module()
    context = module.OriginEditionContext(
        project_id="alt-origin-77",
        family_name="Rossi",
        given_name="Nia",
        runner_name="Glass-Wren",
        namespace="origin.chummer.run/Rossi/Nia/Glass-Wren",
        base_url="https://staging.chummer.run",
    )
    branch = Path(context.resolved_namespace)
    write_json(tmp_path / branch / "portal-publication-index-preflight.receipt.json", {"status": "blocked", "restartRequiredForExistingContainer": True})
    compose = tmp_path / "compose.edge.yml"
    write_compose(compose)
    env_file = tmp_path / "owner.env"
    env_file.write_text("token omitted\n", encoding="utf-8")

    result = module.materialize(
        tmp_path / branch / "portal-restart-plan.receipt.json",
        evidence_root=tmp_path,
        branch=branch,
        compose_file=compose,
        env_file=env_file,
        context=context,
    )

    commands = "\n".join(result["restartCommands"])
    assert "--project-id alt-origin-77" in commands
    assert "--family-name Rossi" in commands
    assert "--given-name Nia" in commands
    assert "--runner-name Glass-Wren" in commands
    assert "--namespace origin.chummer.run/Rossi/Nia/Glass-Wren" in commands
    assert "--base-url https://staging.chummer.run" in commands
    assert "varga-mira-kestrel" not in commands
    assert "Varga" not in commands
    assert "Kestrel" not in commands
    assert result["originEditionContext"]["projectId"] == "alt-origin-77"
