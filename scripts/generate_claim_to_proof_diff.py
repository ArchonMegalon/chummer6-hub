#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from absolute_completion_common import completion_path, read_json, read_yaml, write_yaml


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


def main() -> int:
    route_proof = read_json(completion_path("PUBLIC_ROUTE_POSITIVE_PROOF.generated.json"))
    receipt_proof = read_json(completion_path("RECEIPT_ROUTE_POSITIVE_PROOF.generated.json"))
    package_proof = read_json(completion_path("PACKAGE_ROUTE_AND_API_AUDIT.generated.json"))
    mobile_proof = read_json(completion_path("MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json"))
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
            "/mobile and /play",
            "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json + PUBLIC_SCREENSHOT_MANIFEST.generated.yaml",
            completion_path("MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json"),
            "supported" if mobile_proof.get("status") == "pass" and screenshot_manifest.get("status") == "pass" else "unsupported",
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
