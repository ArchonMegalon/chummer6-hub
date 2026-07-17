from __future__ import annotations

import json
import os
import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "generate_claim_to_proof_diff.py"
PUBLISHED = REPO_ROOT / ".codex-studio" / "published"


def _load_module():
    scripts_dir = str(SCRIPT.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("generate_claim_to_proof_diff", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _mobile_public_entry_payload(*, status: str = "pass") -> dict:
    return {
        "contractName": "chummer.mobile_pwa_public_projection.v2",
        "mode": "source",
        "status": status,
        "failures": [],
        "topology": {
            "privatePlayProfileOnly": True,
            "publicProjectionDefaultOff": True,
            "edgeServiceKeyAbsent": True,
            "edgeUpstreamAbsent": True,
            "portalHasNoPlayDependency": True,
        },
        "gateway": {
            "zeroPublicPaths": True,
            "alwaysNotMatched": True,
            "noHttpClient": True,
            "notInRequestPipeline": True,
        },
        "readiness": {
            "combinedReadyField": True,
            "combinedBodyReturned": True,
            "projectionReadinessRoute": True,
        },
        "roleShell": {
            "playAppliesPrivateHeaders": True,
            "playCanonicalRedirect": True,
            "closedRoleAliases": True,
            "roleFieldsInModel": True,
            "viewUsesModelManifest": True,
            "viewUsesModelRole": True,
            "roleSpecificBody": True,
            "roleSpecificQr": True,
            "installOnly": True,
            "networkClosedCsp": True,
        },
        "retiredEnvAbsent": {
            "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED": True,
            "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED": True,
            "CHUMMER_PUBLIC_PLAY_PROXY_URL": True,
            "CHUMMER_PUBLIC_PLAY_PROXY_API_KEY": True,
        },
        "staticAssets": {
            "contractName": "chummer.public_play_install_assets.v2",
            "status": "pass",
            "failures": [],
        },
    }


def _frontdoor_postdeploy_payload(*, play_target: str = "/mobile/player") -> dict:
    return {
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
        "frontdoorNavigationMobileArtifactContract": "chummer.frontdoor_mobile_install_boundary.v2",
        "frontdoorNavigationMobileArtifactInstallContractSatisfied": True,
        "frontdoorNavigationPublicInstallTargets": ["/build", play_target],
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
    }


def _bridge_public_entry_payload(*, play_target: str = "/mobile/player") -> dict:
    checks = {
        "postdeployContract": True,
        "postdeployPass": True,
        "postdeployNoFailures": True,
        "canonicalBaseUrl": True,
        "browserProofsPass": True,
        "frontdoorProofPass": True,
        "frontdoorContractV2": True,
        "installContractSatisfied": True,
        "publicInstallTargets": True,
        "installOnlyBoundary": True,
        "privateRuntimeAbsent": True,
        "proofClosurePass": True,
    }
    return {
        "hub_mobile_pwa_public_projection": {
            "base_url": "https://chummer.run",
            "pass": True,
            "source_contract": {
                "contractName": "chummer.mobile_pwa_public_projection.v2",
                "mode": "source",
                "pass": True,
                "checks": {
                    "exactContract": True,
                    "passingStatus": True,
                    "noFailures": True,
                    "recognizedMode": True,
                    "staticAssetsPass": True,
                    "sourceTopologyClosed": True,
                    "sourceGatewayClosed": True,
                    "sourceReadinessCombined": True,
                    "sourceInstallOnlyRoleShell": True,
                    "sourceRetiredEnvAbsent": True,
                },
            },
            "public_entry": {
                "contract_name": "chummer.mobile_pwa_frontdoor_install_entry.v2",
                "public_install_targets": ["/build", play_target],
                "build_target": "/build",
                "play_target": play_target,
                "play_surface": "install-only",
                "play_authority": "none",
                "live_session": "unavailable",
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "checks_pass": True,
                "checks": checks,
            },
        }
    }


def _seed_required_claim_proofs(
    root: Path,
    *,
    bridge_boundaries: dict | None = None,
    mobile_public_entry: dict | None = None,
    postdeploy_frontdoor: dict | None = None,
    bridge_proofs: dict | None = None,
) -> None:
    status_payloads = {
        "PUBLIC_ROUTE_POSITIVE_PROOF.generated.json": {"status": "pass", "generated_at_utc": "2026-06-29T00:00:00Z"},
        "RECEIPT_ROUTE_POSITIVE_PROOF.generated.json": {"status": "pass"},
        "PACKAGE_ROUTE_AND_API_AUDIT.generated.json": {"status": "pass"},
        "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json": mobile_public_entry
        if mobile_public_entry is not None
        else _mobile_public_entry_payload(),
        "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": postdeploy_frontdoor
        if postdeploy_frontdoor is not None
        else _frontdoor_postdeploy_payload(),
        "PUBLIC_FORBIDDEN_STRING_SCAN.generated.json": {"status": "pass"},
        "PUBLIC_DOWNLOAD_AUTHORITY.generated.json": {"status": "pass"},
        "DOMAIN_CANONICALIZATION.generated.json": {"status": "pass"},
    }
    for name, payload in status_payloads.items():
        _write_json(root / name, payload)

    _write_json(
        root / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json",
        {
            "contract_name": "chummer.blazor_execution_horizon_bridge",
            "status": "pass",
            "verdict": "mobile_pwa_and_blazor_smoke_integrated_full_matrix_not_proven",
            "boundaries": bridge_boundaries
            if bridge_boundaries is not None
            else {
                "does_not_upgrade_smoke_to_full": True,
                "full_matrix_requires_current_passing_full_scope_receipt": True,
                "hub_mobile_pwa_projection_is_not_blazor_full_execution": True,
            },
            "proofs": bridge_proofs if bridge_proofs is not None else _bridge_public_entry_payload(),
        },
    )
    _write_yaml(root / "PUBLIC_SCREENSHOT_MANIFEST.generated.yaml", {"status": "pass"})


def test_claim_to_proof_diff_requires_blazor_execution_horizon_bridge(tmp_path: Path) -> None:
    _seed_required_claim_proofs(tmp_path)
    env = {
        **os.environ,
        "CHUMMER_COMPLETION_DIR": str(tmp_path),
        "CHUMMER_PUBLISHED_ROOT": str(tmp_path / "empty-published"),
    }

    completed = subprocess.run(
        ["python3", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.returncode == 0

    payload = yaml.safe_load((tmp_path / "CLAIM_TO_PROOF_DIFF.generated.yaml").read_text(encoding="utf-8"))
    claims = {item["required_proof"]: item for item in payload["claims"]}
    bridge_claim = claims["BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json"]

    assert payload["status"] == "pass"
    assert bridge_claim["verdict"] == "supported"
    assert bridge_claim["rewrite_needed"] is False
    assert "without upgrading smoke proof" in bridge_claim["claim"]


def test_claim_to_proof_diff_rejects_bridge_without_smoke_to_full_boundaries(tmp_path: Path) -> None:
    _seed_required_claim_proofs(
        tmp_path,
        bridge_boundaries={
            "does_not_upgrade_smoke_to_full": False,
            "full_matrix_requires_current_passing_full_scope_receipt": True,
        },
    )
    env = {
        **os.environ,
        "CHUMMER_COMPLETION_DIR": str(tmp_path),
        "CHUMMER_PUBLISHED_ROOT": str(tmp_path / "empty-published"),
    }

    completed = subprocess.run(
        ["python3", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1

    payload = yaml.safe_load((tmp_path / "CLAIM_TO_PROOF_DIFF.generated.yaml").read_text(encoding="utf-8"))
    claims = {item["required_proof"]: item for item in payload["claims"]}
    bridge_claim = claims["BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json"]

    assert payload["status"] == "fail"
    assert bridge_claim["verdict"] == "unsupported"
    assert bridge_claim["rewrite_needed"] is True


def test_claim_to_proof_diff_rejects_frontdoor_without_public_build_play_targets(tmp_path: Path) -> None:
    _seed_required_claim_proofs(
        tmp_path,
        postdeploy_frontdoor=_frontdoor_postdeploy_payload(play_target="/play"),
    )
    env = {
        **os.environ,
        "CHUMMER_COMPLETION_DIR": str(tmp_path),
        "CHUMMER_PUBLISHED_ROOT": str(tmp_path / "empty-published"),
    }

    completed = subprocess.run(
        ["python3", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1

    payload = yaml.safe_load((tmp_path / "CLAIM_TO_PROOF_DIFF.generated.yaml").read_text(encoding="utf-8"))
    claims = {item["required_proof"]: item for item in payload["claims"]}
    mobile_claim = claims[
        "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json + "
        "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json + "
        "PUBLIC_SCREENSHOT_MANIFEST.generated.yaml"
    ]

    assert payload["status"] == "fail"
    assert mobile_claim["verdict"] == "unsupported"
    assert mobile_claim["rewrite_needed"] is True
    assert mobile_claim["file_or_route"] == "/, /build, /mobile, and /play"


def test_claim_to_proof_diff_rejects_bridge_without_live_public_entry_evidence(tmp_path: Path) -> None:
    _seed_required_claim_proofs(
        tmp_path,
        bridge_proofs=_bridge_public_entry_payload(play_target="/play"),
    )
    env = {
        **os.environ,
        "CHUMMER_COMPLETION_DIR": str(tmp_path),
        "CHUMMER_PUBLISHED_ROOT": str(tmp_path / "empty-published"),
    }

    completed = subprocess.run(
        ["python3", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1

    payload = yaml.safe_load((tmp_path / "CLAIM_TO_PROOF_DIFF.generated.yaml").read_text(encoding="utf-8"))
    claims = {item["required_proof"]: item for item in payload["claims"]}
    bridge_claim = claims["BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json"]

    assert payload["status"] == "fail"
    assert bridge_claim["verdict"] == "unsupported"
    assert bridge_claim["rewrite_needed"] is True


def test_claim_to_proof_diff_rejects_bridge_with_incomplete_v2_check_set(tmp_path: Path) -> None:
    bridge_proofs = _bridge_public_entry_payload()
    del bridge_proofs["hub_mobile_pwa_public_projection"]["public_entry"]["checks"][
        "proofClosurePass"
    ]
    _seed_required_claim_proofs(tmp_path, bridge_proofs=bridge_proofs)
    env = {
        **os.environ,
        "CHUMMER_COMPLETION_DIR": str(tmp_path),
        "CHUMMER_PUBLISHED_ROOT": str(tmp_path / "empty-published"),
    }

    completed = subprocess.run(
        ["python3", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1

    payload = yaml.safe_load(
        (tmp_path / "CLAIM_TO_PROOF_DIFF.generated.yaml").read_text(encoding="utf-8")
    )
    claims = {item["required_proof"]: item for item in payload["claims"]}
    assert claims["BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json"]["verdict"] == "unsupported"


def test_bridge_predicate_rejects_sparse_source_contract_checks() -> None:
    module = _load_module()
    bridge = {"proofs": _bridge_public_entry_payload()}
    source_contract = bridge["proofs"]["hub_mobile_pwa_public_projection"]["source_contract"]
    source_contract["checks"] = {"passingStatus": True}

    assert module.blazor_bridge_public_entry_supported(bridge) is False


def test_bridge_predicate_rejects_sparse_live_contract_checks() -> None:
    module = _load_module()
    bridge = {"proofs": _bridge_public_entry_payload()}
    source_contract = bridge["proofs"]["hub_mobile_pwa_public_projection"]["source_contract"]
    source_contract["mode"] = "live"
    source_contract["checks"] = {"passingStatus": True}

    assert module.blazor_bridge_public_entry_supported(bridge) is False


def test_claim_to_proof_diff_prefers_published_mobile_receipt_when_completion_receipt_is_stale(tmp_path: Path) -> None:
    module = _load_module()
    stale_path = tmp_path / "completion" / "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json"
    published_root = tmp_path / "published"
    published_path = published_root / "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json"
    _write_json(stale_path, {"status": "pass"})
    _write_json(published_path, _mobile_public_entry_payload())

    previous_published_root = module.PUBLISHED_ROOT
    module.PUBLISHED_ROOT = published_root
    try:
        payload, path = module.prefer_published_when_supported(
            "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json",
            json.loads(stale_path.read_text(encoding="utf-8")),
            stale_path,
            module.mobile_public_entry_supported,
        )
    finally:
        module.PUBLISHED_ROOT = previous_published_root

    assert path == published_path
    assert module.mobile_public_entry_supported(payload) is True


def test_actual_v2_mobile_producer_payload_is_supported() -> None:
    module = _load_module()
    producer_path = REPO_ROOT / "scripts" / "verify_mobile_pwa_public_projection.py"
    spec = importlib.util.spec_from_file_location(
        "verify_mobile_pwa_public_projection_for_claim_test",
        producer_path,
    )
    assert spec is not None and spec.loader is not None
    producer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = producer
    spec.loader.exec_module(producer)

    payload = producer.source_topology(REPO_ROOT)

    assert payload["status"] == "pass", payload["failures"]
    assert module.mobile_public_entry_supported(payload) is True
    assert module.frontdoor_install_entry_supported(
        _frontdoor_postdeploy_payload()
    ) is True


def test_checked_in_claim_to_proof_diff_inputs_include_blazor_bridge() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'read_json_with_published_fallback("BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json")' in source
    assert 'read_json_with_published_fallback("MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json")' in source
    assert "mobile_public_entry_supported" in source
    assert "frontdoor_install_entry_supported" in source
    assert "blazor_bridge_public_entry_supported" in source
    assert "prefer_published_when_supported" in source
    assert "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json" in source
    assert "EXPECTED_PUBLIC_ENTRY_CONTRACT" in source
    assert "EXPECTED_PUBLIC_INSTALL_TARGETS" in source
    assert 'public_entry.get("play_target") == "/mobile/player"' in source
    assert "PUBLISHED_ROOT" in source
    assert "does_not_upgrade_smoke_to_full" in source
    assert "full_matrix_requires_current_passing_full_scope_receipt" in source
    assert "without upgrading smoke proof into a full live public-edge matrix claim" in source
    assert (PUBLISHED / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json").is_file()
