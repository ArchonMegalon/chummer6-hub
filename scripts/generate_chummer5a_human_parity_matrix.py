#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from absolute_completion_common import completion_path, now_iso, write_yaml


UI_ROOT = Path("/docker/chummercomplete/chummer-presentation")
PROOF_PATH = UI_ROOT / ".codex-studio" / "published" / "CHUMMER5A_HUMAN_PARITY_MATRIX_PROOF.generated.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_status(value: object) -> str:
    return str(value or "").strip().lower()


def main() -> int:
    missing_inputs = [str(path) for path in (UI_ROOT, PROOF_PATH) if not path.exists()]
    if missing_inputs:
        payload = {
            "contract_name": "chummer5a.human_parity_matrix_results",
            "generated_at_utc": now_iso(),
            "status": "blocked_external",
            "missing_inputs": missing_inputs,
            "note": "The current audit requires the published Chummer5A human parity proof from chummer-presentation.",
        }
        write_yaml(completion_path("CHUMMER5A_HUMAN_PARITY_MATRIX_RESULTS.generated.yaml"), payload)
        return 0

    proof = load_json(PROOF_PATH)
    family_results = list(proof.get("family_results") or [])
    screenshot_review = dict(proof.get("screenshot_review") or {})
    screenshot_results = list(screenshot_review.get("results") or [])
    ui_audit_summary = dict(proof.get("ui_audit_summary") or {})

    failed_families = [
        row.get("matrix_family_id")
        for row in family_results
        if normalize_status(row.get("status")) != "pass"
    ]
    failed_screenshot_jobs = [
        row.get("job_id")
        for row in screenshot_results
        if normalize_status(row.get("status")) != "pass"
    ]
    visual_no_count = int(ui_audit_summary.get("visual_no_count") or 0)
    behavioral_no_count = int(ui_audit_summary.get("behavioral_no_count") or 0)
    proof_status = normalize_status(proof.get("status"))
    status = (
        "pass"
        if proof_status == "pass"
        and not failed_families
        and not failed_screenshot_jobs
        and visual_no_count == 0
        and behavioral_no_count == 0
        else "failed"
    )

    payload = {
        "contract_name": "chummer5a.human_parity_matrix_results",
        "generated_at_utc": now_iso(),
        "status": status,
        "proof_contract_name": proof.get("contract_name"),
        "proof_path": str(PROOF_PATH),
        "proof_generated_at_utc": proof.get("generated_at"),
        "summary": proof.get("summary"),
        "matrix": proof.get("matrix"),
        "ui_audit_summary": ui_audit_summary,
        "family_pass_count": len(family_results) - len(failed_families),
        "family_failures": failed_families,
        "family_results": [
            {
                "matrix_family_id": row.get("matrix_family_id"),
                "audit_row_id": row.get("audit_row_id"),
                "visual_parity": row.get("visual_parity"),
                "behavioral_parity": row.get("behavioral_parity"),
                "status": row.get("status"),
            }
            for row in family_results
        ],
        "screenshot_review": {
            "path": screenshot_review.get("path"),
            "required_jobs": screenshot_review.get("required_jobs") or [],
            "pass_count": len(screenshot_results) - len(failed_screenshot_jobs),
            "failed_jobs": failed_screenshot_jobs,
        },
        "strict_failure_reasons": proof.get("strict_failure_reasons") or [],
        "evidence_sources": proof.get("evidence_sources") or [str(PROOF_PATH)],
    }
    write_yaml(completion_path("CHUMMER5A_HUMAN_PARITY_MATRIX_RESULTS.generated.yaml"), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
