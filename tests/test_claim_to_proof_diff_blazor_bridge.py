from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "generate_claim_to_proof_diff.py"
PUBLISHED = REPO_ROOT / ".codex-studio" / "published"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _seed_required_claim_proofs(root: Path, *, bridge_boundaries: dict | None = None) -> None:
    status_payloads = {
        "PUBLIC_ROUTE_POSITIVE_PROOF.generated.json": {"status": "pass", "generated_at_utc": "2026-06-29T00:00:00Z"},
        "RECEIPT_ROUTE_POSITIVE_PROOF.generated.json": {"status": "pass"},
        "PACKAGE_ROUTE_AND_API_AUDIT.generated.json": {"status": "pass"},
        "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json": {"status": "pass"},
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
        },
    )
    _write_yaml(root / "PUBLIC_SCREENSHOT_MANIFEST.generated.yaml", {"status": "pass"})


def test_claim_to_proof_diff_requires_blazor_execution_horizon_bridge(tmp_path: Path) -> None:
    _seed_required_claim_proofs(tmp_path)
    env = {**os.environ, "CHUMMER_COMPLETION_DIR": str(tmp_path)}

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
    env = {**os.environ, "CHUMMER_COMPLETION_DIR": str(tmp_path)}

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


def test_checked_in_claim_to_proof_diff_inputs_include_blazor_bridge() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'read_json_with_published_fallback("BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json")' in source
    assert "PUBLISHED_ROOT" in source
    assert "does_not_upgrade_smoke_to_full" in source
    assert "full_matrix_requires_current_passing_full_scope_receipt" in source
    assert "without upgrading smoke proof into a full live public-edge matrix claim" in source
    assert (PUBLISHED / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json").is_file()
