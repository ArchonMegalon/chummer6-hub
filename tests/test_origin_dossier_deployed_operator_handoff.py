from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_dossier_deployed_operator_handoff.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_dossier_deployed_operator_handoff", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def seed_handoff_inputs(root: Path, *, deployed_status: str = "blocked", gold_status: str = "blocked") -> None:
    branch = root / "origin.chummer.run/Varga/Mira/Kestrel"
    deployed_pass = deployed_status == "pass"
    write_json(root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json", {"status": "pass"})
    write_json(branch / "runsite-integration-proof.receipt.json", {"status": "pass"})
    write_json(
        branch / "deployed-chummer-browser-probe.receipt.json",
        {
            "status": deployed_status,
            "blockers": ["missing_deployed_identity_token"] if deployed_status != "pass" else [],
            "next_action": "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN for a real deployed owner session and rerun this probe."
            if deployed_status != "pass"
            else "Inspect deployed route/index/session mismatch and rerun after deployment state is corrected.",
            "blocking_reason": "missing_deployed_identity_token" if deployed_status != "pass" else "",
            "progress": {
                "passedChecks": 21 if deployed_pass else 9,
                "totalChecks": 21,
                "blockedChecks": [] if deployed_pass else ["logged_in_browser_verified", "owner_playback_e2e_verified"],
            },
            "logged_in_browser_verified": deployed_pass,
            "selected_face_cover_visible": deployed_pass,
            "read_tab_visible": deployed_pass,
            "listen_tab_visible": deployed_pass,
            "watch_tab_visible": deployed_pass,
            "canon_audit_tab_visible": deployed_pass,
            "read_gate_verified": deployed_pass,
            "chummer_run_listen_gate_verified": deployed_pass,
            "watch_gate_verified": deployed_pass,
            "cover_route_verified": deployed_pass,
            "book_route_verified": deployed_pass,
            "watch_artifact_nonempty": deployed_pass,
            "cover_artifact_nonempty": deployed_pass,
            "book_artifact_nonempty": deployed_pass,
            "audiobook_share_url_trusted": deployed_pass,
            "dossier_share_url_trusted": deployed_pass,
            "audiobook_share_reachable": deployed_pass,
            "dossier_share_reachable": deployed_pass,
            "owner_playback_e2e_verified": deployed_pass,
            "unauthenticated_detail_redirect_verified": True,
            "unauthenticated_read_redirect_verified": True,
            "unauthenticated_listen_redirect_verified": True,
            "unauthenticated_book_redirect_verified": True,
            "unauthenticated_cover_redirect_verified": True,
            "unauthenticated_video_redirect_verified": True,
            "all_private_routes_login_protected": True,
        },
    )
    write_json(
        root / "ORIGIN_EDITION_GOLD_CURRENT_GAP_AUDIT.generated.json",
        {
            "status": gold_status,
            "failedCodes": ["browser_deployed_probe_blocked:missing_deployed_identity_token"]
            if gold_status != "pass"
            else [],
        },
    )


def test_handoff_is_ready_for_operator_token_without_exposing_secret_values(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    seed_handoff_inputs(tmp_path)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)

    output = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/deployed-operator-handoff.receipt.json"
    result = module.materialize(tmp_path, output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "ready_for_operator_token"
    assert result["updated_at"]
    assert result["next_action"] == "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN for a real deployed owner session and rerun this probe."
    assert "missing_deployed_identity_token" in result["blocking_reason"]
    assert result["progress"]["blockerCount"] == len(result["blockers"])
    assert result["currentEvidence"]["deployedProbeNextAction"] == result["next_action"]
    assert result["currentEvidence"]["deployedProbeBlockingReason"] == "missing_deployed_identity_token"
    assert result["currentEvidence"]["deployedProbeProgress"]["totalChecks"] == 21
    assert result["goalCompletionClaimAllowed"] is False
    assert result["requiredEnv"]["CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN"]["presentInCurrentProcess"] is False
    assert result["requiredEnv"]["CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN"]["valueStoredInReceipt"] is False
    assert result["requiredEnv"]["CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD"]["expectedValueForRelease"] == "1"
    assert result["requiredEnv"]["CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD"]["valueStoredInReceipt"] is False
    assert result["privacy"]["rawSessionTokenExposed"] is False
    assert result["privacy"]["envValuesExposed"] is False
    assert "missing_deployed_identity_token" in result["blockers"]
    assert "--env-file /docker/chummercomplete/chummer.run-services/.env" in serialized
    assert "scripts/materialize_origin_edition_gold_proof_chain.py" in serialized
    assert "--allow-blocked" in serialized
    assert "scripts/materialize_origin_edition_gold_final_verdict.py" in serialized
    assert "scripts/verify_origin_edition_gold_proof_chain.py" in serialized
    assert "--require-gold" in serialized
    assert "scripts/verify_origin_edition_gold_final_verdict.py" in serialized
    assert "FINAL_ORIGIN_EDITION_GOLD_VERDICT.md" in serialized
    assert "ORIGIN_EDITION_GOLD_REQUIREMENT_COVERAGE.generated.json" in serialized
    assert "CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD=1 bash scripts/ai/run_services_verification.sh" in serialized


def test_handoff_uses_origin_edition_context_for_namespace_and_commands(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    context = module.OriginEditionContext.from_env(
        project_id="custom-runner",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
        base_url="https://staging.chummer.run",
    )
    branch = tmp_path / "origin.chummer.run/Case/Ari/Ghost"
    write_json(tmp_path / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json", {"status": "pass"})
    write_json(branch / "runsite-integration-proof.receipt.json", {"status": "pass"})
    write_json(
        branch / "deployed-chummer-browser-probe.receipt.json",
        {
            "status": "blocked",
            "blockers": ["missing_deployed_identity_token"],
            "next_action": "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN for a real deployed owner session and rerun this probe.",
            "blocking_reason": "missing_deployed_identity_token",
            "progress": {"passedChecks": 0, "totalChecks": 21, "blockedChecks": ["owner_playback_e2e_verified"]},
        },
    )
    write_json(tmp_path / "ORIGIN_EDITION_GOLD_CURRENT_GAP_AUDIT.generated.json", {"status": "blocked", "failedCodes": ["blocked"]})
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)

    output = branch / "deployed-operator-handoff.receipt.json"
    result = module.materialize(tmp_path, output, context=context)
    serialized = output.read_text(encoding="utf-8")

    assert result["namespace"] == "origin.chummer.run/Case/Ari/Ghost"
    assert result["projectId"] == "custom-runner"
    assert result["deployedOwnerUrl"] == "https://staging.chummer.run/account/work/origin-dossiers/custom-runner"
    assert "origin.chummer.run/Case/Ari/Ghost/deployed-chummer-browser-probe.receipt.json" in serialized
    assert "--project-id custom-runner" in serialized
    assert "--family-name Case" in serialized
    assert "--given-name Ari" in serialized
    assert "--runner-name Ghost" in serialized
    assert "--namespace origin.chummer.run/Case/Ari/Ghost" in serialized
    assert "--base-url https://staging.chummer.run" in serialized


def test_handoff_passes_only_when_deployed_probe_and_gold_audit_pass(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    seed_handoff_inputs(tmp_path, deployed_status="pass", gold_status="pass")
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "super-secret-owner-token")

    output = tmp_path / "handoff.json"
    result = module.materialize(tmp_path, output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "pass"
    assert result["blocking_reason"] == ""
    assert result["progress"]["blockerCount"] == 0
    assert result["blockers"] == []
    assert result["currentEvidence"]["deployedProbeMissingRequiredFlags"] == []
    assert result["currentEvidence"]["deployedProbeRequiredFlags"]["owner_playback_e2e_verified"] is True
    assert result["requiredEnv"]["CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN"]["presentInCurrentProcess"] is True
    assert result["requiredEnv"]["CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN"]["valueStoredInReceipt"] is False
    assert result["requiredEnv"]["CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD"]["requiredForRelease"] is True
    assert "super-secret-owner-token" not in serialized


def test_handoff_blocks_if_deployed_probe_status_passes_without_owner_playback(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    seed_handoff_inputs(tmp_path, deployed_status="pass", gold_status="pass")
    probe_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/deployed-chummer-browser-probe.receipt.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    probe["owner_playback_e2e_verified"] = False
    probe["blocking_reason"] = "owner_playback_e2e_verified"
    probe["progress"]["blockedChecks"] = ["owner_playback_e2e_verified"]
    write_json(probe_path, probe)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "super-secret-owner-token")

    output = tmp_path / "handoff.json"
    result = module.materialize(tmp_path, output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert "deployed_browser_probe_flag_missing:owner_playback_e2e_verified" in result["blockers"]
    assert result["currentEvidence"]["deployedProbeMissingRequiredFlags"] == ["owner_playback_e2e_verified"]
    assert result["currentEvidence"]["deployedProbeRequiredFlags"]["owner_playback_e2e_verified"] is False
    assert "super-secret-owner-token" not in serialized


def test_handoff_blocks_if_deployed_probe_status_passes_with_untrusted_audiobook_share(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    seed_handoff_inputs(tmp_path, deployed_status="pass", gold_status="pass")
    probe_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/deployed-chummer-browser-probe.receipt.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    probe["audiobook_share_url_trusted"] = False
    probe["blocking_reason"] = "audiobook_share_url_trusted"
    probe["progress"]["blockedChecks"] = ["audiobook_share_url_trusted"]
    write_json(probe_path, probe)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "super-secret-owner-token")

    output = tmp_path / "handoff.json"
    result = module.materialize(tmp_path, output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert "deployed_browser_probe_flag_missing:audiobook_share_url_trusted" in result["blockers"]
    assert result["currentEvidence"]["deployedProbeMissingRequiredFlags"] == ["audiobook_share_url_trusted"]
    assert result["currentEvidence"]["deployedProbeRequiredFlags"]["audiobook_share_url_trusted"] is False
    assert "super-secret-owner-token" not in serialized


def test_handoff_blocks_if_deployed_probe_status_passes_with_empty_movie_artifact(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    seed_handoff_inputs(tmp_path, deployed_status="pass", gold_status="pass")
    probe_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/deployed-chummer-browser-probe.receipt.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    probe["watch_artifact_nonempty"] = False
    probe["blocking_reason"] = "watch_artifact_nonempty"
    probe["progress"]["blockedChecks"] = ["watch_artifact_nonempty"]
    write_json(probe_path, probe)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "super-secret-owner-token")

    output = tmp_path / "handoff.json"
    result = module.materialize(tmp_path, output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert "deployed_browser_probe_flag_missing:watch_artifact_nonempty" in result["blockers"]
    assert result["currentEvidence"]["deployedProbeMissingRequiredFlags"] == ["watch_artifact_nonempty"]
    assert result["currentEvidence"]["deployedProbeRequiredFlags"]["watch_artifact_nonempty"] is False
    assert "super-secret-owner-token" not in serialized


def test_handoff_loads_scoped_env_file_without_exposing_values(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    seed_handoff_inputs(tmp_path, deployed_status="pass", gold_status="pass")
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTH_MODE", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN=super-secret-owner-token",
                "CHUMMER_DEPLOYED_E2E_AUTH_MODE=bearer",
                "UNRELATED_SECRET=must_not_load",
            ]
        ),
        encoding="utf-8",
    )

    output = tmp_path / "handoff.json"
    result = module.materialize(tmp_path, output, env_file)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "pass"
    assert result["envFile"]["provided"] is True
    assert result["envFile"]["loadedKeys"] == [
        "CHUMMER_DEPLOYED_E2E_AUTH_MODE",
        "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN",
    ]
    assert result["envFile"]["valuesStoredInReceipt"] is False
    assert "super-secret-owner-token" not in serialized
    assert "must_not_load" not in serialized
