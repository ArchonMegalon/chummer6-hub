#!/usr/bin/env python3
"""Verify the current Google OAuth operator-evidence request (v2)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import google_oauth_linking_evidence_v2 as evidence_v2


DEFAULT_RECEIPT_PATH = evidence_v2.DEFAULT_REQUEST_PATH


def verify(
    path: Path,
    *,
    require_pass: bool = False,
    portal_release_manifest_path: Path = evidence_v2.DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
    hub_release_manifest_path: Path = evidence_v2.DEFAULT_HUB_RELEASE_MANIFEST_PATH,
    now: datetime | None = None,
) -> tuple[bool, dict[str, Any]]:
    payload, summary, _raw, issues = evidence_v2.verify_request_file(
        path,
        portal_release_manifest_path=portal_release_manifest_path,
        hub_release_manifest_path=hub_release_manifest_path,
        now=now,
    )
    request_status = str(payload.get("status") or "missing")
    if require_pass and request_status != "operator_action_required":
        issues = [*issues, "operator evidence request is not actionable"]
    release = summary.get("release") if isinstance(summary.get("release"), dict) else {}
    result = {
        "contract_name": str(payload.get("contract_name") or ""),
        "path": str(path),
        "status": "pass" if not issues else "fail",
        "require_pass": require_pass,
        "request_status": request_status,
        "request_nonce": summary.get("request_nonce"),
        "request_sha256": summary.get("request_sha256"),
        "request_binding_sha256": summary.get("request_binding_sha256"),
        "release_authority_ready": release.get("ready") is True,
        "release_authority_blockers": list(release.get("blockers") or []),
        "portal_release": release.get("portal") or {},
        "hub_registry_release": release.get("hub_registry") or {},
        "live_release": release.get("live") or {},
        "program_bindings": summary.get("program_bindings") or {},
        "operator_action_still_required": request_status == "operator_action_required",
        "issues": issues,
    }
    return not issues, result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Google OAuth operator evidence request receipt."
    )
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT_PATH)
    parser.add_argument("--require-pass", action="store_true", default=False)
    args = parser.parse_args()
    ok, result = verify(args.receipt, require_pass=args.require_pass)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
