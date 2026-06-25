from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_edition_gold_final_verdict.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_gold_final_verdict", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def seed_artifacts(root: Path, *, ready: bool) -> None:
    blocked_requirements = [] if ready else ["deployed_owner_read_listen_watch_canon"]
    write_json(
        root / "ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json",
        {
            "contractName": "chummer.origin_edition.gold_proof_chain.v1",
            "status": "pass" if ready else "blocked",
            "goalCompletionClaimAllowed": ready,
            "namespace": "origin.chummer.run/Varga/Mira/Kestrel",
            "privacy": {
                "deploymentPerformed": False,
                "envValuesExposed": False,
                "rawCredentialExposed": False,
                "rawSessionTokenExposed": False,
            },
            "stages": [
                {"name": "runsite_integration_proof", "status": "pass"},
                {
                    "name": "requirement_coverage",
                    "status": "pass" if ready else "blocked",
                    "blockedRequirements": blocked_requirements,
                },
            ],
        },
    )
    write_json(
        root / "ORIGIN_EDITION_GOLD_REQUIREMENT_COVERAGE.generated.json",
        {
            "contractName": "chummer.origin_edition.gold_requirement_coverage.v1",
            "status": "pass" if ready else "blocked",
            "goalCompletionClaimAllowed": ready,
            "blockedRequirements": blocked_requirements,
            "requirements": [
                {
                    "id": "deployed_owner_read_listen_watch_canon",
                    "label": "Deployed owner can log into Chummer, see cover, read, listen, watch, and verify Canon Audit",
                    "status": "proved" if ready else "blocked",
                }
            ],
        },
    )


def seed_artifacts_without_namespace(root: Path) -> None:
    write_json(
        root / "ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json",
        {
            "contractName": "chummer.origin_edition.gold_proof_chain.v1",
            "status": "blocked",
            "goalCompletionClaimAllowed": False,
            "privacy": {
                "deploymentPerformed": False,
                "envValuesExposed": False,
                "rawCredentialExposed": False,
                "rawSessionTokenExposed": False,
            },
            "stages": [],
        },
    )
    write_json(
        root / "ORIGIN_EDITION_GOLD_REQUIREMENT_COVERAGE.generated.json",
        {
            "contractName": "chummer.origin_edition.gold_requirement_coverage.v1",
            "status": "blocked",
            "goalCompletionClaimAllowed": False,
            "blockedRequirements": ["deployed_owner_read_listen_watch_canon"],
            "requirements": [],
        },
    )


def test_final_verdict_blocks_until_deployed_owner_requirement_is_proved(tmp_path: Path) -> None:
    module = load_module()
    seed_artifacts(tmp_path, ready=False)

    result = module.materialize(tmp_path, tmp_path / "verdict.md")
    text = (tmp_path / "verdict.md").read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert result["finalVerdict"] == "ORIGIN_EDITION_GOLD_BLOCKED"
    assert result["goalCompletionClaimAllowed"] is False
    assert result["blockedRequirements"] == ["deployed_owner_read_listen_watch_canon"]
    assert "Verdict: `ORIGIN_EDITION_GOLD_BLOCKED`" in text
    assert "Goal completion claim allowed: `false`" in text
    assert "`deployed_owner_read_listen_watch_canon`" in text
    assert "short-lived real owner session token" in text
    assert "Do not claim completion" in text


def test_final_verdict_passes_when_proof_chain_and_coverage_pass(tmp_path: Path) -> None:
    module = load_module()
    seed_artifacts(tmp_path, ready=True)

    result = module.materialize(tmp_path, tmp_path / "verdict.md")
    text = (tmp_path / "verdict.md").read_text(encoding="utf-8")

    assert result["status"] == "pass"
    assert result["finalVerdict"] == "ORIGIN_EDITION_GOLD_READY"
    assert result["goalCompletionClaimAllowed"] is True
    assert result["blockedRequirements"] == []
    assert "Verdict: `ORIGIN_EDITION_GOLD_READY`" in text
    assert "- None." in text


def test_final_verdict_does_not_render_secret_values(tmp_path: Path) -> None:
    module = load_module()
    seed_artifacts(tmp_path, ready=False)

    module.materialize(tmp_path, tmp_path / "verdict.md")
    text = (tmp_path / "verdict.md").read_text(encoding="utf-8")

    assert "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN=" not in text
    assert "rangersofB5" not in text
    assert "api:" not in text


def test_final_verdict_namespace_fallback_uses_supplied_context(tmp_path: Path) -> None:
    module = load_module()
    seed_artifacts_without_namespace(tmp_path)
    context = module.OriginEditionContext.from_env(
        project_id="case-ari-ghost",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
    )

    module.materialize(tmp_path, tmp_path / "verdict.md", context)
    text = (tmp_path / "verdict.md").read_text(encoding="utf-8")

    assert "Namespace: `origin.chummer.run/Case/Ari/Ghost`" in text
    assert "origin.chummer.run/Varga/Mira/Kestrel" not in text
