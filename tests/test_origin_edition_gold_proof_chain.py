from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_edition_gold_proof_chain.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_gold_proof_chain", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fake_modules(calls: list[str], *, matrix_pass: bool) -> SimpleNamespace:
    def deployed_probe(evidence_root, base_url, project_id, output, env_file):
        calls.append("deployed_probe")
        payload = {"status": "pass", "goldEligible": True, "blockers": [], "next_action": "probe done", "blocking_reason": "", "progress": {"totalChecks": 1}}
        write_json(output, payload)
        return payload

    def handoff(evidence_root, output, env_file):
        calls.append("handoff")
        payload = {"status": "pass", "goldEligible": True, "goalCompletionClaimAllowed": False, "blockers": [], "next_action": "handoff done", "blocking_reason": "", "progress": {"blockerCount": 0}}
        write_json(output, payload)
        return payload

    def gold_audit(**kwargs):
        calls.append("gold_audit")
        payload = {"status": "pass", "goalCompletionClaimAllowed": matrix_pass, "failedCodes": [] if matrix_pass else ["blocked"]}
        write_json(kwargs["output"], payload)
        return payload

    def runsite(repo_root, ea_root, evidence_root, output):
        calls.append("runsite")
        payload = {"status": "pass", "goldEligible": matrix_pass, "goalCompletionClaimAllowed": False}
        write_json(output, payload)
        return payload

    def matrix(evidence_root, output):
        calls.append("matrix")
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
            "status": "pass" if matrix_pass else "blocked",
            "goalCompletionClaimAllowed": matrix_pass,
            "blockedRequirements": [] if matrix_pass else ["deployed_owner_read_listen_watch_canon"],
        }
        write_json(output, payload)
        return payload

    return SimpleNamespace(
        deployed_probe=SimpleNamespace(materialize=deployed_probe),
        handoff=SimpleNamespace(materialize=handoff),
        gold_audit=SimpleNamespace(audit=gold_audit),
        runsite=SimpleNamespace(materialize=runsite),
        matrix=SimpleNamespace(materialize=matrix),
        coverage=SimpleNamespace(materialize=coverage),
    )


def test_gold_proof_chain_uses_origin_edition_context_for_branch_and_project(tmp_path: Path) -> None:
    module = load_module()
    calls: list[str] = []
    seen: dict[str, object] = {}

    def deployed_probe(evidence_root, base_url, project_id, output, env_file):
        seen["base_url"] = base_url
        seen["project_id"] = project_id
        seen["deployed_output"] = output
        payload = {"status": "pass", "goldEligible": True, "blockers": []}
        write_json(output, payload)
        return payload

    modules = fake_modules(calls, matrix_pass=True)
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

    assert calls == ["deployed_probe", "handoff", "gold_audit", "runsite", "matrix", "coverage"]
    assert result["status"] == "blocked"
    assert result["updated_at"]
    assert result["next_action"] == "probe done"
    assert "stage:completion_matrix" in result["blocking_reason"]
    assert "requirement:deployed_owner_read_listen_watch_canon" in result["blocking_reason"]
    assert result["progress"]["totalStages"] == 6
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
        ],
    )

    assert module.main() == 1
