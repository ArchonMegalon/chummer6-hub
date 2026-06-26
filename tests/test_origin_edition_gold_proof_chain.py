from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_edition_gold_proof_chain.py"


def load_module():
    seed_origin_context_env()
    spec = importlib.util.spec_from_file_location("origin_edition_gold_proof_chain", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_origin_context_env() -> None:
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_PROJECT_ID", "varga-mira-kestrel")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_FAMILY_NAME", "Varga")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_GIVEN_NAME", "Mira")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_RUNNER_NAME", "Kestrel")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_BASE_URL", "https://chummer.run")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def clear_origin_context_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "CHUMMER_ORIGIN_EDITION_PROJECT_ID",
        "CHUMMER_ORIGIN_EDITION_FAMILY_NAME",
        "CHUMMER_ORIGIN_EDITION_GIVEN_NAME",
        "CHUMMER_ORIGIN_EDITION_RUNNER_NAME",
        "CHUMMER_ORIGIN_EDITION_BASE_URL",
        "CHUMMER_ORIGIN_EDITION_NAMESPACE",
    ):
        monkeypatch.delenv(key, raising=False)


def fake_modules(
    calls: list[str],
    *,
    matrix_pass: bool,
    coverage_pass: bool | None = None,
    seen_contexts: dict[str, object] | None = None,
) -> SimpleNamespace:
    seen_contexts = seen_contexts if seen_contexts is not None else {}
    coverage_pass = matrix_pass if coverage_pass is None else coverage_pass

    def portal_preflight(output, **_kwargs):
        calls.append("portal_preflight")
        payload = {"status": "pass", "restartRequiredForExistingContainer": False, "blockers": [], "next_action": "preflight pass", "blocking_reason": ""}
        write_json(output, payload)
        return payload

    def portal_restart_plan(output, **kwargs):
        calls.append("portal_restart_plan")
        seen_contexts["portal_restart_plan"] = kwargs.get("context")
        seen_contexts["portal_restart_plan_env_file"] = kwargs.get("env_file")
        payload = {"status": "not_required", "blockers": [], "next_action": "restart not required", "blocking_reason": ""}
        write_json(output, payload)
        return payload

    def deployed_probe(evidence_root, base_url, project_id, output, env_file, context=None):
        calls.append("deployed_probe")
        seen_contexts["deployed_probe"] = context
        payload = {"status": "pass", "goldEligible": True, "blockers": [], "next_action": "probe done", "blocking_reason": "", "progress": {"totalChecks": 1}}
        write_json(output, payload)
        return payload

    def handoff(evidence_root, output, env_file, context=None):
        calls.append("handoff")
        seen_contexts["handoff"] = context
        payload = {"status": "pass", "goldEligible": True, "goalCompletionClaimAllowed": False, "blockers": [], "next_action": "handoff done", "blocking_reason": "", "progress": {"blockerCount": 0}}
        write_json(output, payload)
        return payload

    def gold_audit(**kwargs):
        calls.append("gold_audit")
        payload = {"status": "pass", "goalCompletionClaimAllowed": matrix_pass, "failedCodes": [] if matrix_pass else ["blocked"]}
        write_json(kwargs["output"], payload)
        return payload

    def runsite(repo_root, ea_root, evidence_root, output, context=None):
        calls.append("runsite")
        seen_contexts["runsite"] = context
        payload = {"status": "pass", "goldEligible": matrix_pass, "goalCompletionClaimAllowed": False}
        write_json(output, payload)
        return payload

    def matrix(evidence_root, output, context=None):
        calls.append("matrix")
        seen_contexts["matrix"] = context
        payload = {
            "status": "pass" if matrix_pass else "blocked",
            "goalCompletionClaimAllowed": matrix_pass,
            "blockedRows": [] if matrix_pass else ["deployed_user_login_read_listen_watch"],
            "blockedHardGates": [] if matrix_pass else ["gold_audit_completion_claim_allowed"],
        }
        write_json(output, payload)
        return payload

    def coverage(evidence_root, output):
        calls.append("coverage")
        payload = {
            "status": "pass" if coverage_pass else "blocked",
            "goalCompletionClaimAllowed": coverage_pass,
            "blockedRequirements": [] if coverage_pass else ["deployed_owner_read_listen_watch_canon"],
        }
        write_json(output, payload)
        return payload

    return SimpleNamespace(
        portal_preflight=SimpleNamespace(materialize=portal_preflight),
        portal_restart_plan=SimpleNamespace(materialize=portal_restart_plan),
        deployed_probe=SimpleNamespace(materialize=deployed_probe),
        handoff=SimpleNamespace(materialize=handoff),
        gold_audit=SimpleNamespace(audit=gold_audit),
        runsite=SimpleNamespace(materialize=runsite),
        matrix=SimpleNamespace(materialize=matrix),
        coverage=SimpleNamespace(materialize=coverage),
    )


def test_run_chain_without_explicit_context_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    clear_origin_context_env(monkeypatch)

    with pytest.raises(ValueError, match="explicit Origin Edition context required"):
        module.run_chain(
            repo_root=Path("."),
            ea_root=tmp_path,
            evidence_root=tmp_path,
            env_file=None,
            output=tmp_path / "proof.json",
            modules=fake_modules([], matrix_pass=True),
        )


def test_gold_proof_chain_uses_origin_edition_context_for_branch_and_project(tmp_path: Path) -> None:
    module = load_module()
    calls: list[str] = []
    seen: dict[str, object] = {}
    seen_contexts: dict[str, object] = {}

    def deployed_probe(evidence_root, base_url, project_id, output, env_file, context=None):
        seen["base_url"] = base_url
        seen["project_id"] = project_id
        seen["deployed_output"] = output
        seen_contexts["deployed_probe"] = context
        payload = {"status": "pass", "goldEligible": True, "blockers": []}
        write_json(output, payload)
        return payload

    modules = fake_modules(calls, matrix_pass=True, seen_contexts=seen_contexts)
    modules.deployed_probe = SimpleNamespace(materialize=deployed_probe)
    context = module.OriginEditionContext.from_env(
        project_id="custom-runner",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
        base_url="https://staging.chummer.run",
    )

    result = module.run_chain(
        repo_root=tmp_path,
        ea_root=tmp_path,
        evidence_root=tmp_path,
        env_file=None,
        output=tmp_path / "chain.json",
        modules=modules,
        context=context,
    )

    assert result["namespace"] == "origin.chummer.run/Case/Ari/Ghost"
    assert result["projectId"] == "custom-runner"
    assert seen["base_url"] == "https://staging.chummer.run"
    assert seen["project_id"] == "custom-runner"
    assert seen["deployed_output"] == tmp_path / "origin.chummer.run/Case/Ari/Ghost/deployed-chummer-browser-probe.receipt.json"
    assert seen_contexts["deployed_probe"] is context
    assert seen_contexts["portal_restart_plan"] is context
    assert seen_contexts["handoff"] is context
    assert seen_contexts["runsite"] is context
    assert seen_contexts["matrix"] is context


def test_gold_proof_chain_blocks_when_completion_matrix_blocks_and_keeps_env_secret_out(tmp_path: Path) -> None:
    module = load_module()
    calls: list[str] = []
    env_file = tmp_path / ".env"
    env_file.write_text("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN=secret-token\n", encoding="utf-8")

    output = tmp_path / "chain.json"
    result = module.run_chain(
        repo_root=tmp_path,
        ea_root=tmp_path,
        evidence_root=tmp_path,
        env_file=env_file,
        output=output,
        modules=fake_modules(calls, matrix_pass=False),
    )
    serialized = output.read_text(encoding="utf-8")

    assert calls == ["portal_preflight", "portal_restart_plan", "deployed_probe", "handoff", "gold_audit", "handoff", "runsite", "matrix", "coverage"]
    assert result["status"] == "blocked"
    assert result["updated_at"]
    assert result["next_action"] == "probe done"
    assert "stage:completion_matrix" in result["blocking_reason"]
    assert "requirement:deployed_owner_read_listen_watch_canon" in result["blocking_reason"]
    assert result["progress"]["totalStages"] == 8
    assert result["progress"]["blockedRequirements"] == ["deployed_owner_read_listen_watch_canon"]
    assert result["goalCompletionClaimAllowed"] is False
    assert result["stages"][-2]["blockedRows"] == ["deployed_user_login_read_listen_watch"]
    assert result["stages"][-1]["blockedRequirements"] == ["deployed_owner_read_listen_watch_canon"]
    assert result["blockedRequirements"] == ["deployed_owner_read_listen_watch_canon"]
    assert result["envFile"]["valuesStoredInReceipt"] is False
    assert "secret-token" not in serialized


def test_gold_proof_chain_passes_only_when_completion_matrix_allows_claim(tmp_path: Path) -> None:
    module = load_module()
    calls: list[str] = []

    result = module.run_chain(
        repo_root=tmp_path,
        ea_root=tmp_path,
        evidence_root=tmp_path,
        env_file=None,
        output=tmp_path / "chain.json",
        modules=fake_modules(calls, matrix_pass=True),
    )

    assert result["status"] == "pass"
    assert result["finalVerdict"] == "ORIGIN_EDITION_GOLD_READY"
    assert result["goalCompletionClaimAllowed"] is True
    assert result["next_action"] == "Gold proof chain is ready for release handoff. Keep the artifacts archived outside providers."
    assert result["blocking_reason"] == ""
    assert result["progress"]["blockedStages"] == []
    assert result["blockedStages"] == []
    assert result["blockedRequirements"] == []


def test_gold_proof_chain_blocks_when_matrix_passes_but_requirement_coverage_blocks(tmp_path: Path) -> None:
    module = load_module()

    result = module.run_chain(
        repo_root=tmp_path,
        ea_root=tmp_path,
        evidence_root=tmp_path,
        env_file=None,
        output=tmp_path / "chain.json",
        modules=fake_modules([], matrix_pass=True, coverage_pass=False),
    )

    assert result["status"] == "blocked"
    assert result["finalVerdict"] == "ORIGIN_EDITION_GOLD_BLOCKED"
    assert result["goalCompletionClaimAllowed"] is False
    assert result["blockedStages"] == ["requirement_coverage"]
    assert result["blockedRequirements"] == ["deployed_owner_read_listen_watch_canon"]
    assert result["blocking_reason"] == "stage:requirement_coverage,requirement:deployed_owner_read_listen_watch_canon"


def test_gold_proof_chain_blocking_reason_lists_each_blocked_stage_once(tmp_path: Path) -> None:
    module = load_module()

    result = module.run_chain(
        repo_root=tmp_path,
        ea_root=tmp_path,
        evidence_root=tmp_path,
        env_file=None,
        output=tmp_path / "chain.json",
        modules=fake_modules([], matrix_pass=False),
    )

    parts = result["blocking_reason"].split(",")
    stage_parts = [part for part in parts if part.startswith("stage:")]
    assert stage_parts == ["stage:completion_matrix", "stage:requirement_coverage"]
    assert len(stage_parts) == len(set(stage_parts))


def test_main_can_materialize_honest_blocked_chain_without_claiming_gold(tmp_path: Path, monkeypatch) -> None:
    module = load_module()

    def fake_run_chain(**kwargs):
        output = kwargs["output"]
        payload = {
            "contractName": "chummer.origin_edition.gold_proof_chain.v1",
            "status": "blocked",
            "goalCompletionClaimAllowed": False,
        }
        write_json(output, payload)
        return payload

    monkeypatch.setattr(module, "run_chain", fake_run_chain)
    monkeypatch.setattr(
        "sys.argv",
        [
            "materialize_origin_edition_gold_proof_chain.py",
            "--evidence-root",
            str(tmp_path),
            "--project-id",
            "varga-mira-kestrel",
            "--family-name",
            "Varga",
            "--given-name",
            "Mira",
            "--runner-name",
            "Kestrel",
            "--base-url",
            "https://chummer.run",
            "--allow-blocked",
        ],
    )

    assert module.main() == 0
    payload = json.loads((tmp_path / "ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json").read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["goalCompletionClaimAllowed"] is False


def test_main_without_allow_blocked_keeps_non_gold_exit_nonzero(tmp_path: Path, monkeypatch) -> None:
    module = load_module()

    def fake_run_chain(**kwargs):
        output = kwargs["output"]
        payload = {
            "contractName": "chummer.origin_edition.gold_proof_chain.v1",
            "status": "blocked",
            "goalCompletionClaimAllowed": False,
        }
        write_json(output, payload)
        return payload

    monkeypatch.setattr(module, "run_chain", fake_run_chain)
    monkeypatch.setattr(
        "sys.argv",
        [
            "materialize_origin_edition_gold_proof_chain.py",
            "--evidence-root",
            str(tmp_path),
            "--project-id",
            "varga-mira-kestrel",
            "--family-name",
            "Varga",
            "--given-name",
            "Mira",
            "--runner-name",
            "Kestrel",
            "--base-url",
            "https://chummer.run",
        ],
    )

    assert module.main() == 1
