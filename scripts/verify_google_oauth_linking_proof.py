#!/usr/bin/env python3
"""Re-verify Google OAuth proof against current files, never embedded pass claims."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import google_oauth_linking_evidence_v2 as evidence_v2


DEFAULT_RECEIPT_PATH = evidence_v2.DEFAULT_PROOF_PATH


def read_json(path: Path) -> dict[str, Any]:
    payload, _raw = evidence_v2.read_json_object(path)
    return payload


def verify(
    path: Path,
    *,
    require_pass: bool = False,
    request_path: Path = evidence_v2.DEFAULT_REQUEST_PATH,
    evidence_path: Path = evidence_v2.DEFAULT_EVIDENCE_PATH,
    portal_release_manifest_path: Path = evidence_v2.DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
    hub_release_manifest_path: Path = evidence_v2.DEFAULT_HUB_RELEASE_MANIFEST_PATH,
    now: datetime | None = None,
) -> tuple[bool, dict[str, Any]]:
    try:
        payload = read_json(path)
    except evidence_v2.ContractError as exc:
        result = {
            "path": str(path),
            "status": "fail",
            "proof_status": "missing_or_malformed",
            "require_pass": require_pass,
            "issues": [str(exc)],
        }
        return False, result
    summary, issues = evidence_v2.verify_proof_payload(
        payload,
        request_path=request_path,
        evidence_path=evidence_path,
        portal_release_manifest_path=portal_release_manifest_path,
        hub_release_manifest_path=hub_release_manifest_path,
        require_pass=require_pass,
        now=now,
    )
    current_bindings = summary.get("current_bindings")
    current_bindings = current_bindings if isinstance(current_bindings, dict) else {}
    release = current_bindings.get("release")
    release = release if isinstance(release, dict) else {}
    result = {
        "contract_name": str(payload.get("contract_name") or ""),
        "path": str(path),
        "status": "pass" if not issues else "fail",
        "require_pass": require_pass,
        "proof_status": str(payload.get("status") or ""),
        "proof_contract_version": payload.get("proof_contract_version"),
        "release_authority_ready": release.get("ready") is True,
        "release_authority_blockers": list(release.get("blockers") or []),
        "current_request_sha256": (current_bindings.get("request") or {}).get("sha256"),
        "current_request_nonce": (current_bindings.get("request") or {}).get("request_nonce"),
        "current_evidence_sha256": (current_bindings.get("evidence") or {}).get("sha256"),
        "trusted_operator_identity_count": len(evidence_v2.TRUSTED_OPERATOR_IDENTITIES),
        "issues": issues,
    }
    return not issues, result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Google OAuth linking proof receipt.")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT_PATH)
    parser.add_argument("--require-pass", action="store_true", default=False)
    args = parser.parse_args()
    ok, result = verify(args.receipt, require_pass=args.require_pass)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
