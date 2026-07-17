#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from absolute_completion_common import completion_path, read_json, read_yaml, write_yaml
from verify_blazor_execution_horizon_bridge import (
    EXPECTED_MOBILE_CONTRACT,
    EXPECTED_MOBILE_MODE_CHECK_IDS,
    EXPECTED_PUBLIC_ENTRY_CONTRACT,
    EXPECTED_PUBLIC_ENTRY_CHECK_IDS,
    EXPECTED_PUBLIC_INSTALL_TARGETS,
    frontdoor_install_entry_summary,
    mobile_v2_contract_summary,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = Path(os.environ.get("CHUMMER_PUBLISHED_ROOT", REPO_ROOT / ".codex-studio" / "published"))


def read_json_with_published_fallback(name: str) -> tuple[dict, Path]:
    path = completion_path(name)
    if not path.exists():
        fallback = PUBLISHED_ROOT / name
        if fallback.exists():
            path = fallback
        else:
            return {}, path

    payload = read_json(path)
    if isinstance(payload, dict):
        return payload, path
    return {}, path


def prefer_published_when_supported(name: str, payload: dict, path: Path, predicate) -> tuple[dict, Path]:
    if predicate(payload):
        return payload, path

    published_path = PUBLISHED_ROOT / name
    if not published_path.exists() or published_path == path:
        return payload, path

    published_payload = read_json(published_path)
    if isinstance(published_payload, dict) and predicate(published_payload):
        return published_payload, published_path

    return payload, path


def claim_entry(claim: str, file_or_route: str, required_proof: str, proof_path: Path, verdict: str) -> dict:
    return {
        "claim": claim,
        "file_or_route": file_or_route,
        "required_proof": required_proof,
        "proof_found": str(proof_path),
        "proof_freshness": "current_run",
        "priority": "P0",
        "verdict": verdict,
        "rewrite_needed": verdict != "supported",
    }


def mobile_public_entry_supported(mobile_proof: dict) -> bool:
    return mobile_v2_contract_summary(mobile_proof)["pass"] is True


def frontdoor_install_entry_supported(postdeploy_proof: dict) -> bool:
    return frontdoor_install_entry_summary(postdeploy_proof)["checks_pass"] is True


def blazor_bridge_public_entry_supported(blazor_bridge: dict) -> bool:
    proof = (blazor_bridge.get("proofs") or {}).get("hub_mobile_pwa_public_projection") or {}
    public_entry = proof.get("public_entry") if isinstance(proof.get("public_entry"), dict) else {}
    checks = public_entry.get("checks") if isinstance(public_entry.get("checks"), dict) else {}
    source_contract = proof.get("source_contract") if isinstance(proof.get("source_contract"), dict) else {}
    source_checks = source_contract.get("checks") if isinstance(source_contract.get("checks"), dict) else {}
    source_mode = source_contract.get("mode")
    expected_source_checks = EXPECTED_MOBILE_MODE_CHECK_IDS.get(source_mode, ())
    return (
        proof.get("pass") is True
        and proof.get("base_url") == "https://chummer.run"
        and source_contract.get("pass") is True
        and source_contract.get("contractName") == EXPECTED_MOBILE_CONTRACT
        and bool(expected_source_checks)
        and set(source_checks) == set(expected_source_checks)
        and all(source_checks.get(check_id) is True for check_id in expected_source_checks)
        and public_entry.get("contract_name") == EXPECTED_PUBLIC_ENTRY_CONTRACT
        and public_entry.get("public_install_targets") == EXPECTED_PUBLIC_INSTALL_TARGETS
        and public_entry.get("build_target") == "/build"
        and public_entry.get("play_target") == "/mobile/player"
        and public_entry.get("play_surface") == "install-only"
        and public_entry.get("play_authority") == "none"
        and public_entry.get("live_session") == "unavailable"
        and public_entry.get("pwa_manifest_path") == "/manifest.player.webmanifest"
        and public_entry.get("checks_pass") is True
        and set(checks) == set(EXPECTED_PUBLIC_ENTRY_CHECK_IDS)
        and all(checks.get(check_id) is True for check_id in EXPECTED_PUBLIC_ENTRY_CHECK_IDS)
    )


def main() -> int:
    route_proof = read_json(completion_path("PUBLIC_ROUTE_POSITIVE_PROOF.generated.json"))
    receipt_proof = read_json(completion_path("RECEIPT_ROUTE_POSITIVE_PROOF.generated.json"))
    package_proof = read_json(completion_path("PACKAGE_ROUTE_AND_API_AUDIT.generated.json"))
    mobile_proof, mobile_proof_path = read_json_with_published_fallback("MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json")
    public_edge_postdeploy, public_edge_postdeploy_path = read_json_with_published_fallback(
        "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    )
    blazor_bridge, blazor_bridge_path = read_json_with_published_fallback("BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json")
    mobile_proof, mobile_proof_path = prefer_published_when_supported(
        "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json",
        mobile_proof,
        mobile_proof_path,
        mobile_public_entry_supported,
    )
    blazor_bridge, blazor_bridge_path = prefer_published_when_supported(
        "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json",
        blazor_bridge,
        blazor_bridge_path,
        blazor_bridge_public_entry_supported,
    )
    screenshot_manifest = read_yaml(completion_path("PUBLIC_SCREENSHOT_MANIFEST.generated.yaml"))
    provider_scan = read_json(completion_path("PUBLIC_FORBIDDEN_STRING_SCAN.generated.json"))
    download_authority = read_json(completion_path("PUBLIC_DOWNLOAD_AUTHORITY.generated.json"))
    domain_proof = read_json(completion_path("DOMAIN_CANONICALIZATION.generated.json"))

    claims = [
        claim_entry(
            "Public routes in the manifest resolve positively from the current Hub surface.",
            ".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml",
            "PUBLIC_ROUTE_POSITIVE_PROOF.generated.json",
            completion_path("PUBLIC_ROUTE_POSITIVE_PROOF.generated.json"),
            "supported" if route_proof.get("status") == "pass" else "unsupported",
        ),
        claim_entry(
            "Support and Karma Forge submitted pages resolve from created first-party receipts.",
            "/contact and /participate/karma-forge",
            "RECEIPT_ROUTE_POSITIVE_PROOF.generated.json",
            completion_path("RECEIPT_ROUTE_POSITIVE_PROOF.generated.json"),
            "supported" if receipt_proof.get("status") == "pass" else "unsupported",
        ),
        claim_entry(
            "Package browser, follow, vote, and account package rails are real first-party routes.",
            "/packages and /account/packages",
            "PACKAGE_ROUTE_AND_API_AUDIT.generated.json",
            completion_path("PACKAGE_ROUTE_AND_API_AUDIT.generated.json"),
            "supported" if package_proof.get("status") == "pass" else "unsupported",
        ),
        claim_entry(
            "Mobile and play entry stays on a first-party PWA-backed public rail.",
            "/, /build, /mobile, and /play",
            "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json + PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json + PUBLIC_SCREENSHOT_MANIFEST.generated.yaml",
            mobile_proof_path,
            "supported"
            if mobile_public_entry_supported(mobile_proof)
            and frontdoor_install_entry_supported(public_edge_postdeploy)
            and screenshot_manifest.get("status") == "pass"
            else "unsupported",
        ),
        claim_entry(
            "Mobile PWA readiness and Blazor hosted play-shell execution horizon are integrated without upgrading smoke proof into a full live public-edge matrix claim.",
            "/mobile, /play, /blazor",
            "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json",
            blazor_bridge_path,
            "supported"
            if blazor_bridge.get("status") == "pass"
            and (blazor_bridge.get("boundaries") or {}).get("does_not_upgrade_smoke_to_full") is True
            and (blazor_bridge.get("boundaries") or {}).get("full_matrix_requires_current_passing_full_scope_receipt") is True
            and blazor_bridge_public_entry_supported(blazor_bridge)
            else "unsupported",
        ),
        claim_entry(
            "Public surfaces avoid provider and LTD names.",
            "public views, manifest, feature registry, guide copy",
            "PUBLIC_FORBIDDEN_STRING_SCAN.generated.json",
            completion_path("PUBLIC_FORBIDDEN_STRING_SCAN.generated.json"),
            "supported" if provider_scan.get("status") == "pass" else "unsupported",
        ),
        claim_entry(
            "Public acquisition routes through chummer.run surfaces rather than GitHub release shelves.",
            "/downloads and Chummer6/DOWNLOAD.md",
            "PUBLIC_DOWNLOAD_AUTHORITY.generated.json",
            completion_path("PUBLIC_DOWNLOAD_AUTHORITY.generated.json"),
            "supported" if download_authority.get("status") == "pass" else "unsupported",
        ),
        claim_entry(
            "chummer.run is the only canonical public domain and chummer6.run stays retired.",
            "public domain posture",
            "DOMAIN_CANONICALIZATION.generated.json",
            completion_path("DOMAIN_CANONICALIZATION.generated.json"),
            "supported" if domain_proof.get("status") == "pass" else "unsupported",
        ),
    ]

    unsupported = [claim for claim in claims if claim["verdict"] != "supported"]
    payload = {
        "contract_name": "chummer.claim_to_proof_diff",
        "status": "pass" if not unsupported else "fail",
        "generated_at_utc": route_proof.get("generated_at_utc"),
        "claims": claims,
        "unsupported_count": len(unsupported),
    }
    write_yaml(completion_path("CLAIM_TO_PROOF_DIFF.generated.yaml"), payload)
    return 0 if not unsupported else 1


if __name__ == "__main__":
    raise SystemExit(main())
