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


def _mobile_public_entry_payload(*, status: str = "pass", build_final_route: str = "/app?command=character_roster") -> dict:
    return {
        "status": status,
        "checks": [
            {"id": "home_open_chummer_dropdown_routes_build_and_play", "pass": True},
            {"id": "build_route_opens_character_roster", "pass": True},
            {"id": "play_route_opens_pwa_play_shell", "pass": True},
        ],
        "public_entry": {
            "home_open_chummer_dropdown_holds": True,
            "build_route_holds": True,
            "build_final_route": build_final_route,
            "play_shell_holds": True,
            "play_final_route": "/play",
        },
    }


def _bridge_public_entry_payload(*, build_final_route: str = "/app?command=character_roster") -> dict:
    return {
        "hub_mobile_pwa_public_projection": {
            "base_url": "https://chummer.run",
            "pass": True,
            "public_entry": {
                "home_open_chummer_dropdown_holds": True,
                "build_route_holds": True,
                "build_final_route": build_final_route,
                "play_shell_holds": True,
                "play_final_route": "/play",
                "checks_pass": True,
                "checks": {
                    "home_open_chummer_dropdown_routes_build_and_play": {"present": True, "pass": True},
                    "build_route_opens_character_roster": {"present": True, "pass": True},
                    "play_route_opens_pwa_play_shell": {"present": True, "pass": True},
                },
            },
        }
    }


def _seed_required_claim_proofs(
    root: Path,
    *,
    bridge_boundaries: dict | None = None,
    mobile_public_entry: dict | None = None,
    bridge_proofs: dict | None = None,
) -> None:
    status_payloads = {
        "PUBLIC_ROUTE_POSITIVE_PROOF.generated.json": {"status": "pass", "generated_at_utc": "2026-06-29T00:00:00Z"},
        "RECEIPT_ROUTE_POSITIVE_PROOF.generated.json": {"status": "pass"},
        "PACKAGE_ROUTE_AND_API_AUDIT.generated.json": {"status": "pass"},
        "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json": mobile_public_entry
        if mobile_public_entry is not None
        else _mobile_public_entry_payload(),
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


def test_claim_to_proof_diff_rejects_mobile_entry_without_build_play_public_entry(tmp_path: Path) -> None:
    _seed_required_claim_proofs(
        tmp_path,
        mobile_public_entry=_mobile_public_entry_payload(build_final_route="/build"),
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
    mobile_claim = claims["MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json + PUBLIC_SCREENSHOT_MANIFEST.generated.yaml"]

    assert payload["status"] == "fail"
    assert mobile_claim["verdict"] == "unsupported"
    assert mobile_claim["rewrite_needed"] is True
    assert mobile_claim["file_or_route"] == "/, /build, /mobile, and /play"


def test_claim_to_proof_diff_rejects_bridge_without_live_public_entry_evidence(tmp_path: Path) -> None:
    _seed_required_claim_proofs(
        tmp_path,
        bridge_proofs=_bridge_public_entry_payload(build_final_route="/build"),
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


def test_checked_in_claim_to_proof_diff_inputs_include_blazor_bridge() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'read_json_with_published_fallback("BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json")' in source
    assert 'read_json_with_published_fallback("MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json")' in source
    assert "mobile_public_entry_supported" in source
    assert "blazor_bridge_public_entry_supported" in source
    assert "prefer_published_when_supported" in source
    assert "home_open_chummer_dropdown_routes_build_and_play" in source
    assert "build_route_opens_character_roster" in source
    assert "play_route_opens_pwa_play_shell" in source
    assert "/app?command=character_roster" in source
    assert "PUBLISHED_ROOT" in source
    assert "does_not_upgrade_smoke_to_full" in source
    assert "full_matrix_requires_current_passing_full_scope_receipt" in source
    assert "without upgrading smoke proof into a full live public-edge matrix claim" in source
    assert (PUBLISHED / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json").is_file()
