from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_blazor_execution_horizon_bridge.py"
RECEIPT = REPO_ROOT / ".codex-studio" / "published" / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json"
MANIFEST = REPO_ROOT / ".codex-studio" / "published" / "compile.manifest.json"
REFRESH_SCRIPT = REPO_ROOT / "scripts" / "refresh_qwen35_estate_gate_receipts.py"
FINAL_GOLD_JANITOR = REPO_ROOT / "scripts" / "final_gold_janitor.py"
RUN_GOLD_JANITOR = REPO_ROOT / "scripts" / "run_gold_janitor.py"


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    assert isinstance(payload, dict)
    return payload


def test_blazor_execution_horizon_bridge_script_binds_hub_and_presentation_proofs() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json" in source
    assert "BLAZOR_PWA_PUBLIC_EDGE_PROOF.generated.json" in source
    assert "BLAZOR_PUBLIC_EDGE_EXECUTION_HORIZON.generated.json" in source
    assert "near_term_hosted_smoke_execution" in source
    assert "mid_term_full_live_public_edge_execution_matrix" in source
    assert "home_open_chummer_dropdown_routes_build_and_play" in source
    assert "build_route_opens_character_roster" in source
    assert "play_route_opens_pwa_play_shell" in source
    assert "/app?command=character_roster" in source
    assert "does_not_upgrade_smoke_to_full" in source
    assert "full_scope_requires_current_passing_full_receipt" in source
    assert "CHUMMER_WORKSPACE_ROOT" in source
    assert "/docker/chummercomplete" in source


def test_blazor_execution_horizon_bridge_receipt_is_honest_about_full_matrix() -> None:
    completed = subprocess.run(
        ["python3", str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "blazor_execution_horizon_bridge:ok" in completed.stdout

    payload = _read_json(RECEIPT)
    horizon = payload["proofs"]["blazor_hosted_execution_horizon"]

    assert payload["contract_name"] == "chummer.blazor_execution_horizon_bridge"
    assert payload["status"] == "pass"
    assert payload["proofs"]["hub_mobile_pwa_public_projection"]["pass"] is True
    mobile_public_entry = payload["proofs"]["hub_mobile_pwa_public_projection"]["public_entry"]
    assert payload["proofs"]["hub_mobile_pwa_public_projection"]["base_url"] == "https://chummer.run"
    assert mobile_public_entry["home_open_chummer_dropdown_holds"] is True
    assert mobile_public_entry["build_route_holds"] is True
    assert mobile_public_entry["build_final_route"] == "/app?command=character_roster"
    assert mobile_public_entry["play_shell_holds"] is True
    assert mobile_public_entry["play_final_route"] == "/play"
    assert mobile_public_entry["checks_pass"] is True
    for check_id in (
        "home_open_chummer_dropdown_routes_build_and_play",
        "build_route_opens_character_roster",
        "play_route_opens_pwa_play_shell",
    ):
        assert mobile_public_entry["checks"][check_id]["present"] is True
        assert mobile_public_entry["checks"][check_id]["pass"] is True
    assert payload["proofs"]["blazor_hosted_pwa_public_edge"]["pass"] is True
    assert horizon["near_term_smoke_status"] == "proven"
    assert payload["boundaries"]["does_not_upgrade_smoke_to_full"] is True
    assert payload["boundaries"]["full_matrix_requires_current_passing_full_scope_receipt"] is True
    assert payload["proofs"]["blazor_hosted_execution_horizon"]["long_term_full_browser_parity_path"]
    assert payload["proofs"]["blazor_hosted_execution_horizon"]["long_term_full_browser_parity_status"] in {"not_proven", "proven"}
    assert payload["boundaries"]["does_not_upgrade_full_matrix_to_long_term_browser_parity"] is True
    if horizon["mid_term_full_matrix_status"] != "proven":
        assert payload["verdict"] == "mobile_pwa_and_blazor_smoke_integrated_full_matrix_not_proven"
        assert horizon["mid_term_full_covered_workflow_family_count"] < horizon["mid_term_full_required_workflow_family_count"]
        assert horizon["long_term_full_browser_parity_status"] == "not_proven"
        assert horizon["long_term_full_browser_parity_proof_status"] in {"pass", "passed", "ready", "fail", "missing"}
    else:
        if horizon["long_term_full_browser_parity_status"] == "proven":
            assert payload["verdict"] == "mobile_pwa_and_blazor_full_matrix_and_long_term_browser_parity_integrated"
        else:
            assert payload["verdict"] == "mobile_pwa_and_blazor_full_matrix_integrated"


def test_blazor_execution_horizon_bridge_is_indexed_and_refreshable() -> None:
    manifest = _read_json(MANIFEST)
    refresh_source = REFRESH_SCRIPT.read_text(encoding="utf-8")
    final_gold_source = FINAL_GOLD_JANITOR.read_text(encoding="utf-8")
    run_gold_source = RUN_GOLD_JANITOR.read_text(encoding="utf-8")

    assert "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json" in manifest["artifacts"]
    assert "python3 scripts/verify_blazor_execution_horizon_bridge.py" in refresh_source
    assert '"blazor_execution_horizon_bridge": PUBLISHED_ROOT / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json"' in final_gold_source
    assert '["python3", "scripts/verify_blazor_execution_horizon_bridge.py"]' in final_gold_source
    assert '["python3", "scripts/verify_blazor_execution_horizon_bridge.py"]' in run_gold_source
