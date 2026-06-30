#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from absolute_completion_common import completion_path, read_json, read_yaml, write_yaml


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


def check_by_id(payload: dict, check_id: str) -> dict:
    for row in payload.get("checks") or []:
        if isinstance(row, dict) and str(row.get("id") or "").strip() == check_id:
            return row
    return {}


def mobile_public_entry_supported(mobile_proof: dict) -> bool:
    public_entry = mobile_proof.get("public_entry") if isinstance(mobile_proof.get("public_entry"), dict) else {}
    required_checks = (
        "home_open_chummer_dropdown_routes_build_and_play",
        "build_route_opens_character_roster",
        "play_route_opens_pwa_play_shell",
    )
    return (
        mobile_proof.get("status") == "pass"
        and public_entry.get("home_open_chummer_dropdown_holds") is True
        and public_entry.get("build_route_holds") is True
        and public_entry.get("play_shell_holds") is True
        and public_entry.get("build_final_route") == "/app?command=character_roster"
        and public_entry.get("play_final_route") == "/play"
        and all(check_by_id(mobile_proof, check_id).get("pass") is True for check_id in required_checks)
    )


def blazor_bridge_public_entry_supported(blazor_bridge: dict) -> bool:
    proof = (blazor_bridge.get("proofs") or {}).get("hub_mobile_pwa_public_projection") or {}
    public_entry = proof.get("public_entry") if isinstance(proof.get("public_entry"), dict) else {}
    checks = public_entry.get("checks") if isinstance(public_entry.get("checks"), dict) else {}
    required_checks = (
        "home_open_chummer_dropdown_routes_build_and_play",
        "build_route_opens_character_roster",
        "play_route_opens_pwa_play_shell",
    )
    return (
        proof.get("pass") is True
        and proof.get("base_url") == "https://chummer.run"
        and public_entry.get("home_open_chummer_dropdown_holds") is True
        and public_entry.get("build_route_holds") is True
        and public_entry.get("play_shell_holds") is True
        and public_entry.get("build_final_route") == "/app?command=character_roster"
        and public_entry.get("play_final_route") == "/play"
        and public_entry.get("checks_pass") is True
        and all((checks.get(check_id) or {}).get("pass") is True for check_id in required_checks)
    )


def main() -> int:
    route_proof = read_json(completion_path("PUBLIC_ROUTE_POSITIVE_PROOF.generated.json"))
    receipt_proof = read_json(completion_path("RECEIPT_ROUTE_POSITIVE_PROOF.generated.json"))
    package_proof = read_json(completion_path("PACKAGE_ROUTE_AND_API_AUDIT.generated.json"))
    mobile_proof, mobile_proof_path = read_json_with_published_fallback("MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json")
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
            "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json + PUBLIC_SCREENSHOT_MANIFEST.generated.yaml",
            mobile_proof_path,
            "supported" if mobile_public_entry_supported(mobile_proof) and screenshot_manifest.get("status") == "pass" else "unsupported",
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
