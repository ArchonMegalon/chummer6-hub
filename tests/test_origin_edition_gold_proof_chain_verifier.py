from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_origin_edition_gold_proof_chain.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_gold_proof_chain_verifier", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def proof_payload(*, status: str = "blocked") -> dict:
    sha = "a" * 64
    blocked_stages = [
        "portal_publication_index_preflight",
        "portal_restart_plan",
        "deployed_browser_probe",
        "gold_gap_audit",
        "completion_matrix",
        "requirement_coverage",
    ]
    return {
        "contractName": "chummer.origin_edition.gold_proof_chain.v1",
        "status": status,
        "updated_at": "2026-06-25T13:00:00Z",
        "next_action": "Gold proof chain is ready for release handoff. Keep the artifacts archived outside providers."
        if status == "pass"
        else "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN for a real deployed owner session and rerun this probe.",
        "blocking_reason": ""
        if status == "pass"
        else "stage:deployed_browser_probe,requirement:deployed_owner_read_listen_watch_canon",
        "progress": {
            "passedStages": 8 if status == "pass" else 2,
            "totalStages": 8,
            "blockedStages": [] if status == "pass" else blocked_stages,
            "blockedRequirements": [] if status == "pass" else ["deployed_owner_read_listen_watch_canon"],
        },
        "goalCompletionClaimAllowed": status == "pass",
        "envFile": {"valuesStoredInReceipt": False},
        "privacy": {
            "rawCredentialExposed": False,
            "rawSessionTokenExposed": False,
            "envValuesExposed": False,
            "deploymentPerformed": False,
        },
        "blockedStages": [] if status == "pass" else blocked_stages,
        "stages": [
            {
                "name": "portal_publication_index_preflight",
                "path": "/evidence/portal-publication-index-preflight.receipt.json",
                "sha256": sha,
                "status": "pass" if status == "pass" else "blocked",
                "blockers": [] if status == "pass" else ["running_portal_publication_index_env_missing"],
            },
            {
                "name": "portal_restart_plan",
                "path": "/evidence/portal-restart-plan.receipt.json",
                "sha256": sha,
                "status": "not_required" if status == "pass" else "awaiting_explicit_restart_approval",
                "blockers": [],
                "approvalGate": "" if status == "pass" else "explicit_user_deploy_or_restart_approval_required",
                "safeToExecuteAfterApproval": status != "pass",
            },
            {
                "name": "deployed_browser_probe",
                "path": "/evidence/deployed-chummer-browser-probe.receipt.json",
                "sha256": sha,
                "status": status,
                "blockers": []
                if status == "pass"
                else ["missing_deployed_identity_token", "owner_playback_e2e_verified"],
            },
            {
                "name": "deployed_operator_handoff",
                "path": "/evidence/deployed-operator-handoff.receipt.json",
                "sha256": sha,
                "status": "pass" if status == "pass" else "ready_for_operator_token",
                "blockers": []
                if status == "pass"
                else ["deployed_browser_probe_flag_missing:owner_playback_e2e_verified"],
            },
            {"name": "gold_gap_audit", "path": "/evidence/gold-gap.json", "sha256": sha, "status": status},
            {"name": "runsite_integration_proof", "path": "/evidence/runsite.json", "sha256": sha, "status": "pass"},
            {
                "name": "completion_matrix",
                "path": "/evidence/matrix.json",
                "sha256": sha,
                "status": status,
                "blockedRows": [] if status == "pass" else ["deployed_user_login_read_listen_watch"],
                "blockedHardGates": [] if status == "pass" else ["gold_audit_completion_claim_allowed"],
            },
            {
                "name": "requirement_coverage",
                "path": "/evidence/coverage.json",
                "sha256": sha,
                "status": status,
                "blockedRequirements": [] if status == "pass" else ["deployed_owner_read_listen_watch_canon"],
            },
        ],
    }


def test_verifier_accepts_expected_blocked_deployed_owner_gap(tmp_path: Path) -> None:
    module = load_module()
    receipt = write_json(tmp_path / "chain.json", proof_payload(status="blocked"))

    ok, issues = module.verify(receipt)

    assert ok is True
    assert issues == []


def test_verifier_require_gold_rejects_blocked_chain(tmp_path: Path) -> None:
    module = load_module()
    receipt = write_json(tmp_path / "chain.json", proof_payload(status="blocked"))

    ok, issues = module.verify(receipt, require_gold=True)

    assert ok is False
    assert "proof_chain_not_pass" in issues
    assert "goal_completion_not_allowed" in issues


def test_verifier_require_gold_accepts_clean_pass_chain(tmp_path: Path) -> None:
    module = load_module()
    receipt = write_json(tmp_path / "chain.json", proof_payload(status="pass"))

    ok, issues = module.verify(receipt, require_gold=True)

    assert ok is True
    assert issues == []


def test_verifier_require_gold_rejects_pass_chain_with_stale_stage_blockers(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="pass")
    payload["blockedStages"] = ["completion_matrix"]
    payload["stages"][2]["blockers"] = ["owner_playback_e2e_verified"]
    payload["stages"][6]["blockedRows"] = ["deployed_user_login_read_listen_watch"]
    payload["stages"][6]["blockedHardGates"] = ["gold_audit_completion_claim_allowed"]
    payload["stages"][7]["blockedRequirements"] = ["deployed_owner_read_listen_watch_canon"]
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt, require_gold=True)

    assert ok is False
    assert "gold_chain_has_blocked_stages" in issues
    assert "gold_stage_has_blockers:deployed_browser_probe" in issues
    assert "gold_stage_has_blocked_rows:completion_matrix" in issues
    assert "gold_stage_has_blocked_hard_gates:completion_matrix" in issues
    assert "gold_stage_has_blocked_requirements:requirement_coverage" in issues


def test_verifier_rejects_pass_chain_without_completion_claim_even_without_require_gold(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="pass")
    payload["goalCompletionClaimAllowed"] = False
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt)

    assert ok is False
    assert "pass_chain_goal_completion_not_allowed" in issues


def test_verifier_rejects_pass_chain_with_blocked_rollups_even_without_require_gold(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="pass")
    payload["blockedStages"] = ["requirement_coverage"]
    payload["progress"]["blockedStages"] = ["requirement_coverage"]
    payload["blockedRequirements"] = ["deployed_owner_read_listen_watch_canon"]
    payload["progress"]["blockedRequirements"] = ["deployed_owner_read_listen_watch_canon"]
    payload["stages"][7]["status"] = "blocked"
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt)

    assert ok is False
    assert "pass_chain_has_blocked_stages" in issues
    assert "pass_chain_has_progress_blocked_stages" in issues
    assert "pass_chain_has_blocked_requirements" in issues
    assert "pass_chain_has_progress_blocked_requirements" in issues


def test_verifier_require_gold_rejects_pass_chain_with_non_pass_stage(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="pass")
    payload["stages"][4]["status"] = "blocked"
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt, require_gold=True)

    assert ok is False
    assert "gold_stage_not_pass:gold_gap_audit" in issues


def test_verifier_rejects_secret_marker_in_receipt(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="blocked")
    payload["debug"] = "Bearer secret-token Cookie: api.telegram.org/bot123 UNMIXR_API_KEY=leaked"
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt)

    assert ok is False
    assert "forbidden_secret_marker:Bearer " in issues
    assert "forbidden_secret_marker:secret-token" in issues
    assert "forbidden_secret_marker:Cookie:" in issues
    assert "forbidden_secret_marker:api.telegram.org/bot" in issues
    assert "forbidden_secret_marker:UNMIXR_API_KEY=" in issues


def test_verifier_rejects_blocked_stage_rollup_mismatch(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="blocked")
    payload["blockedStages"] = ["deployed_browser_probe"]
    payload["progress"]["blockedStages"] = ["deployed_browser_probe"]
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt)

    assert ok is False
    assert "blocked_stages_do_not_match_stage_statuses" in issues


def test_verifier_rejects_progress_blocked_stage_mismatch(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="blocked")
    payload["progress"]["blockedStages"] = ["deployed_browser_probe"]
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt)

    assert ok is False
    assert "progress_blocked_stages_do_not_match_top_level" in issues


def test_verifier_rejects_progress_stage_counts_mismatch(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="blocked")
    payload["progress"]["totalStages"] = 5
    payload["progress"]["passedStages"] = 6
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt)

    assert ok is False
    assert "progress_total_stages_mismatch" in issues
    assert "progress_passed_stages_mismatch" in issues


def test_verifier_rejects_missing_normalized_chain_status(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="blocked")
    payload.pop("next_action")
    payload.pop("blocking_reason")
    payload.pop("progress")
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt)

    assert ok is False
    assert "next_action_missing" in issues
    assert "blocked_chain_missing_blocking_reason" in issues
    assert "progress_total_stages_missing" in issues


def test_verifier_rejects_blocked_chain_without_owner_playback_blockers(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="blocked")
    payload["stages"][2]["blockers"] = ["missing_deployed_identity_token"]
    payload["stages"][3]["blockers"] = ["deployed_browser_probe_not_pass"]
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt)

    assert ok is False
    assert "deployed_probe_missing_owner_playback_blocker" in issues
    assert "handoff_missing_owner_playback_blocker" in issues


def test_verifier_rejects_stage_without_hash_bound_receipt(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="blocked")
    payload["stages"][4]["sha256"] = ""
    payload["stages"][4]["path"] = ""
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt)

    assert ok is False
    assert "stage_sha256_invalid:gold_gap_audit" in issues
    assert "stage_path_missing:gold_gap_audit" in issues


def test_verifier_rejects_blocked_chain_when_runsite_stage_is_not_pass(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="blocked")
    payload["stages"][5]["status"] = "blocked"
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt)

    assert ok is False
    assert "runsite_integration_proof_not_pass" in issues


def test_verifier_rejects_completion_matrix_without_gold_audit_hard_gate(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="blocked")
    payload["stages"][6]["blockedHardGates"] = []
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt)

    assert ok is False
    assert "completion_matrix_missing_gold_audit_hard_gate" in issues


def test_verifier_rejects_blocked_chain_with_unexpected_requirement_coverage_blocker(tmp_path: Path) -> None:
    module = load_module()
    payload = proof_payload(status="blocked")
    payload["stages"][7]["blockedRequirements"] = ["m4b_premium_audiobook_packaging"]
    receipt = write_json(tmp_path / "chain.json", payload)

    ok, issues = module.verify(receipt)

    assert ok is False
    assert "requirement_coverage_unexpected_blocked_requirements" in issues
