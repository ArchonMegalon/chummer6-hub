from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_blazor_execution_horizon_bridge.py"
RECEIPT = REPO_ROOT / ".codex-studio" / "published" / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json"
MANIFEST = REPO_ROOT / ".codex-studio" / "published" / "compile.manifest.json"
REFRESH_SCRIPT = REPO_ROOT / "scripts" / "refresh_qwen35_estate_gate_receipts.py"
FINAL_GOLD_JANITOR = REPO_ROOT / "scripts" / "final_gold_janitor.py"
RUN_GOLD_JANITOR = REPO_ROOT / "scripts" / "run_gold_janitor.py"


def _load_script_module(path: Path, name: str):
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    assert "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json" in source
    assert "chummer.mobile_pwa_public_projection.v2" in source
    assert "chummer.frontdoor_mobile_install_boundary.v2" in source
    assert "chummer.mobile_pwa_frontdoor_install_entry.v2" in source
    assert 'EXPECTED_PUBLIC_INSTALL_TARGETS = ["/build", "/mobile/player"]' in source
    assert '"play_surface":' in source
    assert '"play_authority":' in source
    assert "does_not_upgrade_smoke_to_full" in source
    assert "full_scope_requires_current_passing_full_receipt" in source
    assert "CHUMMER_WORKSPACE_ROOT" in source
    assert "/docker/chummercomplete" in source


def test_frontdoor_summary_requires_exact_postdeploy_contract_and_empty_failures() -> None:
    module = _load_script_module(
        SCRIPT,
        "verify_blazor_execution_horizon_bridge_fail_closed_test",
    )

    wrong_contract = module.frontdoor_install_entry_summary(
        {"contractName": "chummer.public_edge_postdeploy_gate.preview", "status": "pass", "failures": []}
    )
    structured_failure = module.frontdoor_install_entry_summary(
        {
            "contractName": "chummer.public_edge_postdeploy_gate.v1",
            "status": "pass",
            "failures": ["frontdoor proof drifted"],
        }
    )

    assert wrong_contract["checks"]["postdeployContract"] is False
    assert structured_failure["checks"]["postdeployNoFailures"] is False
    assert wrong_contract["checks_pass"] is False
    assert structured_failure["checks_pass"] is False


def test_mobile_v2_summary_rejects_structured_failures() -> None:
    mobile_module = _load_script_module(
        REPO_ROOT / "scripts" / "verify_mobile_pwa_public_projection.py",
        "verify_mobile_pwa_public_projection_for_failure_test",
    )
    module = _load_script_module(
        SCRIPT,
        "verify_blazor_execution_horizon_bridge_mobile_failure_test",
    )
    payload = mobile_module.source_topology(REPO_ROOT)
    payload["failures"] = ["source proof drifted"]

    summary = module.mobile_v2_contract_summary(payload)

    assert summary["checks"]["noFailures"] is False
    assert summary["pass"] is False


def test_mobile_v2_summary_rejects_sparse_live_probe_checks() -> None:
    module = _load_script_module(
        SCRIPT,
        "verify_blazor_execution_horizon_bridge_sparse_live_probe_test",
    )
    payload = {
        "contractName": module.EXPECTED_MOBILE_CONTRACT,
        "mode": "live",
        "baseUrl": "https://chummer.run",
        "status": "pass",
        "failures": [],
        "staticAssets": {
            "contractName": "chummer.public_pwa_static_assets.v1",
            "assetContractName": "chummer.public_play_install_assets.v2",
            "status": "pass",
            "failures": [],
        },
        "readiness": {
            "checks": {
                check_id: True
                for check_id in module.EXPECTED_MOBILE_LIVE_READINESS_CHECK_IDS
            }
        },
        "roleProbes": {
            probe_id: {"checks": {"dummy": True}}
            for probe_id in module.EXPECTED_MOBILE_LIVE_ROLE_PROBE_IDS
        },
    }

    summary = module.mobile_v2_contract_summary(payload)

    assert summary["checks"]["liveRoleProbesComplete"] is True
    assert summary["checks"]["liveRoleProbesPass"] is False
    assert summary["pass"] is False


def test_mobile_v2_summary_rejects_sparse_source_evidence() -> None:
    module = _load_script_module(
        SCRIPT,
        "verify_blazor_execution_horizon_bridge_sparse_source_test",
    )
    payload = {
        "contractName": module.EXPECTED_MOBILE_CONTRACT,
        "mode": "source",
        "status": "pass",
        "failures": [],
        "staticAssets": {
            "contractName": "chummer.public_play_install_assets.v2",
            "status": "pass",
            "failures": [],
        },
        "topology": {
            key: True for key in module.EXPECTED_MOBILE_SOURCE_TOPOLOGY_CHECK_IDS
        },
        "gateway": {"zeroPublicPaths": True, "noHttpClient": True},
        "readiness": {"combinedBodyReturned": True},
        "roleShell": {
            "playAppliesPrivateHeaders": True,
            "playCanonicalRedirect": True,
            "roleSpecificQr": True,
            "installOnly": True,
            "networkClosedCsp": True,
        },
        "retiredEnvAbsent": {},
    }

    summary = module.mobile_v2_contract_summary(payload)

    assert summary["checks"]["sourceTopologyClosed"] is True
    assert summary["checks"]["sourceGatewayClosed"] is False
    assert summary["checks"]["sourceReadinessCombined"] is False
    assert summary["checks"]["sourceInstallOnlyRoleShell"] is False
    assert summary["checks"]["sourceRetiredEnvAbsent"] is False
    assert summary["pass"] is False


def test_blazor_execution_horizon_bridge_accepts_actual_v2_producer_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    mobile_module = _load_script_module(
        REPO_ROOT / "scripts" / "verify_mobile_pwa_public_projection.py",
        "verify_mobile_pwa_public_projection_for_bridge_test",
    )
    module = _load_script_module(
        SCRIPT,
        "verify_blazor_execution_horizon_bridge_for_test",
    )
    mobile_path = tmp_path / "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json"
    postdeploy_path = tmp_path / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    output_path = tmp_path / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json"
    mobile_path.write_text(
        json.dumps(mobile_module.source_topology(REPO_ROOT), indent=2) + "\n",
        encoding="utf-8",
    )
    postdeploy_path.write_text(
        json.dumps(
            {
                "contractName": "chummer.public_edge_postdeploy_gate.v1",
                "status": "pass",
                "failures": [],
                "baseUrl": "https://chummer.run",
                "browserPlaywrightStatus": "pass",
                "frontdoorNavigationPlaywrightRuntimeResolutionMode": (
                    "validated_local_node_modules_exact_lock_version"
                ),
                "frontdoorNavigationPlaywrightPackageVersion": "1.60.0",
                "frontdoorNavigationPlaywrightPackageJsonSha256": "e" * 64,
                "frontdoorNavigationPlaywrightCliSha256": "f" * 64,
                "frontdoorNavigationStatus": "pass",
                "frontdoorNavigationMobileArtifactContract": (
                    "chummer.frontdoor_mobile_install_boundary.v2"
                ),
                "frontdoorNavigationMobileArtifactInstallContractSatisfied": True,
                "frontdoorNavigationPublicInstallTargets": ["/build", "/mobile/player"],
                "frontdoorNavigationDeviceRouting": "auto_ua_ch_mobile_direct",
                "frontdoorNavigationPlaySurface": "install-only",
                "frontdoorNavigationPlayAuthority": "none",
                "frontdoorNavigationLiveSession": "unavailable",
                "frontdoorNavigationPwaManifestPath": "/manifest.player.webmanifest",
                "frontdoorNavigationLiveTurnCompanionShell": False,
                "frontdoorNavigationPrivateBrowserStateKeys": 0,
                "frontdoorNavigationPlayApiRequests": 0,
                "frontdoorNavigationBlazorCircuitRequests": 0,
                "frontdoorNavigationAnalyticsRequests": 0,
                "frontdoorNavigationPrivateQueryRequests": 0,
                "frontdoorNavigationPageErrors": [],
                "frontdoorNavigationProofClosureStatus": "pass",
                "frontdoorNavigationProofClosureSha256": "d" * 64,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "MOBILE_PWA_PROOF", mobile_path)
    monkeypatch.setattr(module, "PUBLIC_EDGE_POSTDEPLOY_PROOF", postdeploy_path)
    monkeypatch.setattr(module, "OUTPUT_PATH", output_path)

    assert module.main() == 0

    payload = _read_json(output_path)
    horizon = payload["proofs"]["blazor_hosted_execution_horizon"]
    final_gold = _load_script_module(
        FINAL_GOLD_JANITOR,
        "final_gold_janitor_for_bridge_compatibility_test",
    )
    final_gold_public_entry = final_gold.blazor_bridge_public_entry_summary(payload)

    assert payload["contract_name"] == "chummer.blazor_execution_horizon_bridge"
    assert payload["status"] == "pass"
    assert payload["proofs"]["hub_mobile_pwa_public_projection"]["pass"] is True
    mobile_public_entry = payload["proofs"]["hub_mobile_pwa_public_projection"]["public_entry"]
    assert payload["proofs"]["hub_mobile_pwa_public_projection"]["base_url"] == "https://chummer.run"
    assert payload["proofs"]["hub_mobile_pwa_public_projection"]["contract_name"] == (
        "chummer.mobile_pwa_public_projection.v2"
    )
    assert payload["proofs"]["hub_mobile_pwa_public_projection"]["source_contract"]["pass"] is True
    assert mobile_public_entry["contract_name"] == "chummer.mobile_pwa_frontdoor_install_entry.v2"
    assert mobile_public_entry["public_install_targets"] == ["/build", "/mobile/player"]
    assert mobile_public_entry["build_target"] == "/build"
    assert mobile_public_entry["play_target"] == "/mobile/player"
    assert mobile_public_entry["play_surface"] == "install-only"
    assert mobile_public_entry["play_authority"] == "none"
    assert mobile_public_entry["live_session"] == "unavailable"
    assert mobile_public_entry["pwa_manifest_path"] == "/manifest.player.webmanifest"
    assert mobile_public_entry["checks_pass"] is True
    assert all(mobile_public_entry["checks"].values())
    assert final_gold_public_entry["pass"] is True
    assert final_gold_public_entry["public_install_targets"] == ["/build", "/mobile/player"]
    assert final_gold_public_entry["play_target"] == "/mobile/player"
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
