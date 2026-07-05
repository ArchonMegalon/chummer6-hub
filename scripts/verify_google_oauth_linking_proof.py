#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROOF_SCRIPT_PATH = SCRIPT_DIR / "materialize_google_oauth_linking_proof.py"
DEFAULT_RECEIPT_PATH = SCRIPT_DIR.parents[0] / ".codex-studio" / "published" / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_google_oauth_linking_proof", PROOF_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"google_oauth_linking_proof_module_load_failed:{PROOF_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object")
    return payload


def verify(path: Path, *, require_pass: bool = False) -> tuple[bool, dict[str, Any]]:
    if not path.is_file():
        result = {
            "path": str(path),
            "status": "fail",
            "issues": [f"missing_google_oauth_linking_proof:{path}"],
            "require_pass": require_pass,
        }
        return False, result

    payload = read_json(path)
    module = load_module()
    ok, issues = module.verify_receipt(
        payload,
        require_pass=require_pass,
        allow_operator_evidence_missing=not require_pass,
    )
    operator_request_artifacts = payload.get("operator_request_artifacts") if isinstance(payload.get("operator_request_artifacts"), dict) else {}
    operator_evidence = payload.get("operator_end_to_end_evidence") if isinstance(payload.get("operator_end_to_end_evidence"), dict) else {}
    result = {
        "contract_name": str(payload.get("contract_name") or "").strip(),
        "path": str(path),
        "status": "pass" if ok else "fail",
        "require_pass": require_pass,
        "proof_status": str(payload.get("status") or "").strip(),
        "issues": issues,
        "quick_handoff_pass": bool(dict(payload.get("quick_handoff_probe") or {}).get("pass")),
        "signed_in_link_status": str(dict(payload.get("signed_in_link_handoff") or {}).get("status") or "").strip(),
        "operator_evidence_pass": bool(operator_evidence.get("pass")),
        "operator_request_artifacts_pass": bool(operator_request_artifacts.get("pass")),
        "operator_request_artifacts_failures": list(operator_request_artifacts.get("failures") or []),
    }
    return ok, result


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
