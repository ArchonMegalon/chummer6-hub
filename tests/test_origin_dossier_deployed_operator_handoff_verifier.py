from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_origin_dossier_deployed_operator_handoff.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_dossier_deployed_operator_handoff_verifier", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def handoff_payload(*, status: str = "ready_for_operator_token") -> dict:
    pass_state = status == "pass"
    blockers = [] if pass_state else ["missing_deployed_identity_token"]
    required_flags = {
        "logged_in_browser_verified": pass_state,
        "owner_playback_e2e_verified": pass_state,
    }
    return {
        "contractName": "chummer.origin_edition.deployed_operator_handoff.v1",
        "status": status,
        "updated_at": "2026-06-25T13:00:00Z",
        "next_action": "Gold proof chain is ready for release handoff." if pass_state else "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN for a real deployed owner session and rerun this probe.",
        "blocking_reason": "" if pass_state else ",".join(blockers),
        "progress": {"blockerCount": len(blockers)},
        "goalCompletionClaimAllowed": False,
        "requiredEnv": {
            "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN": {
                "required": True,
                "presentInCurrentProcess": pass_state,
                "valueStoredInReceipt": False,
            },
            "CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD": {
                "requiredForRelease": True,
                "expectedValueForRelease": "1",
                "valueStoredInReceipt": False,
            },
        },
        "envFile": {"valuesStoredInReceipt": False},
        "requiredCommands": [
            "python3 scripts/materialize_origin_dossier_deployed_browser_probe.py --env-file /docker/chummercomplete/chummer.run-services/.env --evidence-root /docker/chummercomplete/.tmp/origin-dossier-fresh-gold",
            "python3 scripts/audit_origin_dossier_gold_e2e.py --pretty --require-pass",
            "python3 scripts/materialize_origin_edition_gold_proof_chain.py --allow-blocked",
            "python3 scripts/materialize_origin_edition_gold_final_verdict.py --allow-blocked",
            "python3 scripts/verify_origin_edition_gold_proof_chain.py --require-gold",
            "python3 scripts/verify_origin_edition_gold_final_verdict.py --verdict /docker/chummercomplete/.tmp/origin-dossier-fresh-gold/FINAL_ORIGIN_EDITION_GOLD_VERDICT.md",
            "CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD=1 bash scripts/ai/run_services_verification.sh",
        ],
        "currentEvidence": {
            "deployedProbeRequiredFlags": required_flags,
            "deployedProbeMissingRequiredFlags": [] if pass_state else list(required_flags),
            "deployedProbeNextAction": "Gold proof chain is ready for release handoff." if pass_state else "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN for a real deployed owner session and rerun this probe.",
            "deployedProbeBlockingReason": "" if pass_state else ",".join(blockers),
            "deployedProbeProgress": {"passedChecks": 2 if pass_state else 0, "totalChecks": 2, "blockedChecks": [] if pass_state else list(required_flags)},
        },
        "blockers": blockers,
        "privacy": {
            "deploymentPerformed": False,
            "envValuesExposed": False,
            "rawCredentialExposed": False,
            "rawSessionTokenExposed": False,
        },
    }


def test_verifier_accepts_ready_for_operator_token_handoff(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "handoff.json"
    write_json(path, handoff_payload())

    ok, issues = module.verify(path)

    assert ok is True
    assert issues == []


def test_verifier_accepts_pass_handoff_when_require_pass(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "handoff.json"
    write_json(path, handoff_payload(status="pass"))

    ok, issues = module.verify(path, require_pass=True)

    assert ok is True
    assert issues == []


def test_verifier_rejects_missing_final_verdict_verification_command(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "handoff.json"
    payload = handoff_payload()
    payload["requiredCommands"] = [
        command for command in payload["requiredCommands"] if "verify_origin_edition_gold_final_verdict.py" not in command
    ]
    write_json(path, payload)

    ok, issues = module.verify(path)

    assert ok is False
    assert any(issue.startswith("required_command_missing:verify_origin_edition_gold_final_verdict.py") for issue in issues)


def test_verifier_rejects_ready_handoff_without_missing_token_blocker(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "handoff.json"
    payload = handoff_payload()
    payload["blockers"] = []
    write_json(path, payload)

    ok, issues = module.verify(path)

    assert ok is False
    assert "ready_handoff_missing_identity_token_blocker" in issues


def test_verifier_rejects_missing_deployed_probe_status_propagation(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "handoff.json"
    payload = handoff_payload()
    payload["currentEvidence"].pop("deployedProbeNextAction")
    payload["currentEvidence"].pop("deployedProbeBlockingReason")
    payload["currentEvidence"].pop("deployedProbeProgress")
    write_json(path, payload)

    ok, issues = module.verify(path)

    assert ok is False
    assert "deployed_probe_next_action_missing" in issues
    assert "deployed_probe_blocking_reason_missing" in issues
    assert "deployed_probe_progress_missing" in issues


def test_verifier_rejects_secret_marker(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "handoff.json"
    write_json(path, handoff_payload())
    path.write_text(path.read_text(encoding="utf-8") + "\nBearer leaked\n", encoding="utf-8")

    ok, issues = module.verify(path)

    assert ok is False
    assert "forbidden_secret_marker:Bearer " in issues


def test_default_handoff_path_uses_origin_edition_env_context(monkeypatch, tmp_path: Path) -> None:
    module = load_module()
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_EVIDENCE_ROOT", str(tmp_path))
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_PROJECT_ID", "case-ari-ghost")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_FAMILY_NAME", "Case")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_GIVEN_NAME", "Ari")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_RUNNER_NAME", "Ghost")
    monkeypatch.delenv("CHUMMER_ORIGIN_EDITION_NAMESPACE", raising=False)

    assert module.deployed_operator_handoff_from_env() == (
        tmp_path / "origin.chummer.run/Case/Ari/Ghost/deployed-operator-handoff.receipt.json"
    )
