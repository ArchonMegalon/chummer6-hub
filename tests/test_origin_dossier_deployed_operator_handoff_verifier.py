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
    module = load_module()
    pass_state = status == "pass"
    blockers = [] if pass_state else ["missing_deployed_owner_session"]
    required_flags = {
        flag: pass_state for flag in module.REQUIRED_DEPLOYED_PROBE_FLAGS
    }
    return {
        "contractName": "chummer.origin_edition.deployed_operator_handoff.v1",
        "status": status,
        "updated_at": "2026-06-25T13:00:00Z",
        "next_action": "Gold proof chain is ready for release handoff." if pass_state else "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN, CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN, CHUMMER_DEPLOYED_E2E_COOKIE_HEADER, or CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER for a real deployed owner session and rerun this probe.",
        "blocking_reason": "" if pass_state else ",".join(blockers),
        "progress": {"blockerCount": len(blockers)},
        "goalCompletionClaimAllowed": False,
        "context": {
            "projectId": "varga-mira-kestrel",
            "familyName": "Varga",
            "givenName": "Mira",
            "runnerName": "Kestrel",
            "namespace": "origin.chummer.run/Varga/Mira/Kestrel",
            "baseUrl": "https://chummer.run",
        },
        "requiredEnv": {
            "deployedOwnerSession": {
                "required": True,
                "acceptedKeys": [
                    "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN",
                    "CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN",
                    "CHUMMER_DEPLOYED_E2E_COOKIE_HEADER",
                    "CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER",
                ],
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
            "python3 scripts/materialize_origin_dossier_deployed_state_import.py --live-import /docker/chummercomplete/.tmp/origin-dossier-fresh-gold/ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json --host-state-root /var/lib/docker/volumes/chummer6-hub_chummer-run-api-state/_data --container-state-root /app/state --output-receipt /docker/chummercomplete/.tmp/origin-dossier-fresh-gold/origin.chummer.run/Varga/Mira/Kestrel/deployed-state-import.receipt.json",
            "python3 scripts/materialize_origin_dossier_deployed_browser_probe.py --env-file /docker/chummercomplete/chummer.run-services/.env --evidence-root /docker/chummercomplete/.tmp/origin-dossier-fresh-gold --project-id varga-mira-kestrel --family-name Varga --given-name Mira --runner-name Kestrel --namespace origin.chummer.run/Varga/Mira/Kestrel --base-url https://chummer.run",
            "python3 scripts/audit_origin_dossier_gold_e2e.py --pretty --require-pass",
            "python3 scripts/materialize_origin_edition_gold_proof_chain.py --project-id varga-mira-kestrel --family-name Varga --given-name Mira --runner-name Kestrel --namespace origin.chummer.run/Varga/Mira/Kestrel --base-url https://chummer.run --allow-blocked",
            "python3 scripts/materialize_origin_edition_gold_final_verdict.py --project-id varga-mira-kestrel --family-name Varga --given-name Mira --runner-name Kestrel --namespace origin.chummer.run/Varga/Mira/Kestrel --base-url https://chummer.run --allow-blocked",
            "python3 scripts/verify_origin_edition_gold_proof_chain.py --require-gold",
            "python3 scripts/verify_origin_edition_gold_final_verdict.py --verdict /docker/chummercomplete/.tmp/origin-dossier-fresh-gold/FINAL_ORIGIN_EDITION_GOLD_VERDICT.md",
            "CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD=1 bash scripts/ai/run_services_verification.sh",
        ],
        "currentEvidence": {
            "deployedProbeRequiredFlags": required_flags,
            "deployedProbeMissingRequiredFlags": [] if pass_state else list(required_flags),
            "deployedProbeNextAction": "Gold proof chain is ready for release handoff." if pass_state else "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN, CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN, CHUMMER_DEPLOYED_E2E_COOKIE_HEADER, or CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER for a real deployed owner session and rerun this probe.",
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


def test_verifier_rejects_rerun_commands_without_explicit_origin_context(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "handoff.json"
    payload = handoff_payload()
    payload["requiredCommands"] = [
        "python3 scripts/materialize_origin_dossier_deployed_browser_probe.py --env-file .env --evidence-root /tmp/evidence",
        "python3 scripts/audit_origin_dossier_gold_e2e.py --pretty --require-pass",
        "python3 scripts/materialize_origin_edition_gold_proof_chain.py --allow-blocked",
        "python3 scripts/materialize_origin_edition_gold_final_verdict.py --allow-blocked",
        "python3 scripts/verify_origin_edition_gold_proof_chain.py --require-gold",
        "python3 scripts/verify_origin_edition_gold_final_verdict.py --verdict /tmp/verdict.md",
        "CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD=1 bash scripts/ai/run_services_verification.sh",
    ]
    write_json(path, payload)

    ok, issues = module.verify(path)

    assert ok is False
    assert "required_context_argument_missing:--project-id" in issues
    assert "required_context_argument_missing:--namespace" in issues
    assert "required_context_argument_missing:materialize_origin_edition_gold_final_verdict.py:--project-id" in issues


def test_verifier_rejects_final_verdict_materialization_without_explicit_context(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "handoff.json"
    payload = handoff_payload()
    payload["requiredCommands"] = [
        command.replace(
            " --project-id varga-mira-kestrel --family-name Varga --given-name Mira --runner-name Kestrel --namespace origin.chummer.run/Varga/Mira/Kestrel --base-url https://chummer.run",
            "",
        )
        if "materialize_origin_edition_gold_final_verdict.py" in command
        else command
        for command in payload["requiredCommands"]
    ]
    write_json(path, payload)

    ok, issues = module.verify(path)

    assert ok is False
    assert "required_context_argument_missing:materialize_origin_edition_gold_final_verdict.py:--project-id" in issues
    assert "required_context_argument_missing:materialize_origin_edition_gold_final_verdict.py:--base-url" in issues


def test_verifier_rejects_ready_handoff_without_missing_token_blocker(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "handoff.json"
    payload = handoff_payload()
    payload["blockers"] = []
    write_json(path, payload)

    ok, issues = module.verify(path)

    assert ok is False
    assert "ready_handoff_missing_owner_session_blocker" in issues


def test_verifier_rejects_handoff_with_stale_required_probe_flag_set(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "handoff.json"
    payload = handoff_payload(status="pass")
    payload["currentEvidence"]["deployedProbeRequiredFlags"].pop("watch_artifact_nonempty")
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert any(issue.startswith("deployed_probe_required_flags_missing:") for issue in issues)


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
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\nBearer leaked\napi.telegram.org/bot123\nsecret-session\nUNMIXR_API_KEY=leaked\n",
        encoding="utf-8",
    )

    ok, issues = module.verify(path)

    assert ok is False
    assert "forbidden_secret_marker:Bearer " in issues
    assert "forbidden_secret_marker:api.telegram.org/bot" in issues
    assert "forbidden_secret_marker:secret-session" in issues
    assert "forbidden_secret_marker:UNMIXR_API_KEY=" in issues


def test_default_handoff_path_uses_origin_edition_env_context(monkeypatch, tmp_path: Path) -> None:
    module = load_module()
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_EVIDENCE_ROOT", str(tmp_path))
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_PROJECT_ID", "case-ari-ghost")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_FAMILY_NAME", "Case")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_GIVEN_NAME", "Ari")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_RUNNER_NAME", "Ghost")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_BASE_URL", "https://chummer.run")
    monkeypatch.delenv("CHUMMER_ORIGIN_EDITION_NAMESPACE", raising=False)

    assert module.deployed_operator_handoff_from_env() == (
        tmp_path / "origin.chummer.run/Case/Ari/Ghost/deployed-operator-handoff.receipt.json"
    )
