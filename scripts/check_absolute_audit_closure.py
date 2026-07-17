#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from materialize_google_oauth_linking_proof import verify_receipt as verify_google_oauth_linking_receipt


RUN_SERVICES_ROOT = Path("/docker/chummercomplete/chummer.run-services")
PRESENTATION_ROOT = Path("/docker/chummercomplete/chummer-presentation")
CORE_ROOT = Path("/docker/chummercomplete/chummer-core-engine")
PASS_STATUSES = {"pass", "passed", "ready", "ok", "green"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def normalized_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def status_is_pass(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    status = str(payload.get("status") or "").strip().lower()
    failures = normalized_strings(payload.get("failures"))
    failed_gates = normalized_strings(payload.get("failed_gates"))
    return status in PASS_STATUSES and not failures and not failed_gates


def resolve_path(root: Path, candidate: Any) -> Path | None:
    if not isinstance(candidate, str):
        return None
    text = candidate.strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else root / path


def command_matches(payload: dict[str, Any], expected: list[str]) -> bool:
    command = payload.get("command")
    return isinstance(command, list) and command == expected


def receipt_path_list_ok(root: Path, values: Any, *, minimum: int = 1) -> tuple[bool, str]:
    if not isinstance(values, list) or len(values) < minimum:
        return False, "missing evidence_receipts"
    resolved = [resolve_path(root, value) for value in values]
    if any(path is None for path in resolved):
        return False, "evidence_receipts contains invalid path entries"
    missing = [str(path) for path in resolved if not path.is_file()]
    if missing:
        return False, f"missing evidence receipts: {', '.join(missing)}"
    return True, f"evidence_receipts={len(resolved)}"


def rel(path: Path) -> str:
    return str(path)


def build_check(
    *,
    key: str,
    abs_ids: list[str],
    label: str,
    path: Path,
    ok: bool,
    detail: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "abs_ids": abs_ids,
        "label": label,
        "path": rel(path),
        "ok": ok,
        "detail": detail,
    }


def receipt_check(
    *,
    key: str,
    abs_ids: list[str],
    label: str,
    path: Path,
    validator,
) -> dict[str, Any]:
    payload = load_json(path)
    if payload is None:
        return build_check(
            key=key,
            abs_ids=abs_ids,
            label=label,
            path=path,
            ok=False,
            detail="missing receipt",
        )
    ok, detail = validator(payload)
    return build_check(
        key=key,
        abs_ids=abs_ids,
        label=label,
        path=path,
        ok=ok,
        detail=detail,
    )


def validate_live_route_proof(payload: dict[str, Any]) -> tuple[bool, str]:
    summary = payload.get("summary") or {}
    failed_count = summary.get("failed_count")
    route_count = summary.get("route_count")
    ok = isinstance(failed_count, int) and failed_count == 0 and isinstance(route_count, int) and route_count > 0
    return ok, f"route_count={route_count} failed_count={failed_count}"


def validate_canonical_domain(payload: dict[str, Any]) -> tuple[bool, str]:
    canonical = payload.get("canonical_public_domain")
    status = str(payload.get("status") or "").strip().lower()
    domain_status = payload.get("domain_status") or {}
    retired_alias = domain_status.get("chummer6.run")
    ok = status_is_pass(payload) and canonical == "chummer.run" and retired_alias == "not_used"
    return ok, (
        f"status={status or 'missing'} canonical_public_domain={canonical!r} "
        f"chummer6.run={retired_alias!r}"
    )


def validate_pass(payload: dict[str, Any]) -> tuple[bool, str]:
    ok = status_is_pass(payload)
    return ok, f"status={payload.get('status')!r}"


def validate_human_parity(payload: dict[str, Any]) -> tuple[bool, str]:
    matrix = payload.get("matrix") or {}
    row_count = matrix.get("row_count")
    family_count = matrix.get("family_count")
    ok = status_is_pass(payload) and isinstance(row_count, int) and row_count > 0 and isinstance(family_count, int) and family_count > 0
    return ok, f"status={payload.get('status')!r} row_count={row_count} family_count={family_count}"


def validate_live_support_proof(payload: dict[str, Any]) -> tuple[bool, str]:
    routes_checked = payload.get("routes_checked")
    stdout = str(payload.get("stdout") or "")
    required_routes = {"/contact", "/help", "/faq", "/home/access", "/account/support"}
    ok = (
        status_is_pass(payload)
        and payload.get("base_url") == "https://chummer.run"
        and payload.get("script") == "scripts/check-support-case-flow.py"
        and command_matches(payload, ["python3", "scripts/check-support-case-flow.py"])
        and isinstance(routes_checked, list)
        and required_routes.issubset(set(str(route) for route in routes_checked))
        and "ok" in stdout.lower()
    )
    return ok, (
        f"status={payload.get('status')!r} "
        f"base_url={payload.get('base_url')!r} script={payload.get('script')!r} "
        f"routes_checked={len(routes_checked) if isinstance(routes_checked, list) else 'missing'} "
        f"stdout_ok={'ok' in stdout.lower()}"
    )


def validate_live_oauth_linking_proof(payload: dict[str, Any]) -> tuple[bool, str]:
    ok, issues = verify_google_oauth_linking_receipt(payload, require_pass=True)
    return ok, (
        f"status={payload.get('status')!r} base_url={payload.get('base_url')!r} "
        f"proof_contract_version={payload.get('proof_contract_version')!r} "
        f"issues={issues}"
    )


def validate_desktop_execution_proof(payload: dict[str, Any]) -> tuple[bool, str]:
    receipts = payload.get("receipts")
    run_context = payload.get("run_context")
    required = {
        "screenshot_review": PRESENTATION_ROOT / ".codex-studio" / "published" / "CHUMMER5A_SCREENSHOT_REVIEW_GATE.generated.json",
        "workflow_execution": PRESENTATION_ROOT / ".codex-studio" / "published" / "DESKTOP_WORKFLOW_EXECUTION_GATE.generated.json",
        "visual_familiarity": PRESENTATION_ROOT / ".codex-studio" / "published" / "DESKTOP_VISUAL_FAMILIARITY_EXIT_GATE.generated.json",
        "human_parity_matrix": PRESENTATION_ROOT / ".codex-studio" / "published" / "CHUMMER5A_HUMAN_PARITY_MATRIX_PROOF.generated.json",
    }
    receipt_paths_ok = isinstance(receipts, dict)
    if receipt_paths_ok:
        for key, path in required.items():
            candidate = resolve_path(PRESENTATION_ROOT, receipts.get(key))
            if candidate is None or candidate != path or not path.is_file():
                receipt_paths_ok = False
                break
    ok = (
        status_is_pass(payload)
        and isinstance(run_context, dict)
        and isinstance(run_context.get("timestamp"), str)
        and receipt_paths_ok
    )
    return ok, (
        f"status={payload.get('status')!r} "
        f"run_context_timestamp={bool(isinstance(run_context, dict) and isinstance(run_context.get('timestamp'), str))} "
        f"receipts_bound={receipt_paths_ok}"
    )


def validate_portable_receipts_audit(payload: dict[str, Any]) -> tuple[bool, str]:
    scanned_artifact_count = payload.get("scanned_artifact_count")
    machine_specific_hits = payload.get("machine_specific_hits")
    ok = (
        status_is_pass(payload)
        and isinstance(scanned_artifact_count, int)
        and scanned_artifact_count > 0
        and isinstance(machine_specific_hits, list)
        and len(machine_specific_hits) == 0
    )
    return ok, (
        f"status={payload.get('status')!r} scanned_artifact_count={scanned_artifact_count!r} "
        f"machine_specific_hits={len(machine_specific_hits) if isinstance(machine_specific_hits, list) else 'missing'}"
    )


def validate_acceptance_receipt(payload: dict[str, Any], *, ruleset: str) -> tuple[bool, str]:
    evidence_ok, evidence_detail = receipt_path_list_ok(CORE_ROOT, payload.get("evidence_receipts"), minimum=1)
    allowed = payload.get("serious_implementation_claim") == "allowed"
    ok = status_is_pass(payload) and payload.get("ruleset") == ruleset and allowed and evidence_ok
    return ok, (
        f"status={payload.get('status')!r} ruleset={payload.get('ruleset')!r} "
        f"serious_implementation_claim={payload.get('serious_implementation_claim')!r} {evidence_detail}"
    )


def validate_sr5_boundary_receipt(payload: dict[str, Any]) -> tuple[bool, str]:
    boundary_state = str(payload.get("claim_status") or "").strip().lower()
    ok = (
        status_is_pass(payload)
        and payload.get("ruleset") == "SR5"
        and boundary_state in {"bounded", "limited", "partial"}
    )
    return ok, (
        f"status={payload.get('status')!r} ruleset={payload.get('ruleset')!r} "
        f"claim_status={boundary_state or 'missing'}"
    )


def validate_claim_retirement_receipt(payload: dict[str, Any], *, ruleset: str) -> tuple[bool, str]:
    claim_status = str(payload.get("claim_status") or "").strip().lower()
    ok = (
        status_is_pass(payload)
        and payload.get("ruleset") == ruleset
        and claim_status in {"retired", "not_supported", "disallowed"}
    )
    return ok, (
        f"status={payload.get('status')!r} ruleset={payload.get('ruleset')!r} "
        f"claim_status={claim_status or 'missing'}"
    )


def validate_sr5_closure() -> dict[str, Any]:
    acceptance_path = CORE_ROOT / ".codex-studio" / "published" / "SR5_ACCEPTANCE_PROOF.generated.json"
    boundary_path = CORE_ROOT / ".codex-studio" / "published" / "SR5_CLAIM_BOUNDARY.generated.json"
    acceptance = load_json(acceptance_path)
    boundary = load_json(boundary_path)
    acceptance_ok, acceptance_detail = validate_acceptance_receipt(acceptance or {}, ruleset="SR5")
    if acceptance_ok:
        return build_check(
            key="sr5_closure",
            abs_ids=["ABS-006"],
            label="SR5 closure",
            path=acceptance_path,
            ok=True,
            detail=acceptance_detail,
        )
    boundary_ok, boundary_detail = validate_sr5_boundary_receipt(boundary or {})
    if boundary_ok:
        return build_check(
            key="sr5_closure",
            abs_ids=["ABS-006"],
            label="SR5 closure",
            path=boundary_path,
            ok=True,
            detail=boundary_detail,
        )
    return build_check(
        key="sr5_closure",
        abs_ids=["ABS-006"],
        label="SR5 closure",
        path=acceptance_path,
        ok=False,
        detail="need SR5_ACCEPTANCE_PROOF.generated.json or SR5_CLAIM_BOUNDARY.generated.json",
    )


def validate_ruleset_decision(
    *,
    ruleset_id: str,
    abs_id: str,
) -> dict[str, Any]:
    upper = ruleset_id.upper()
    acceptance_path = CORE_ROOT / ".codex-studio" / "published" / f"{upper}_ACCEPTANCE_PROOF.generated.json"
    retirement_path = CORE_ROOT / ".codex-studio" / "published" / f"{upper}_CLAIM_RETIREMENT.generated.json"
    acceptance = load_json(acceptance_path)
    retirement = load_json(retirement_path)
    acceptance_ok, acceptance_detail = validate_acceptance_receipt(acceptance or {}, ruleset=upper)
    if acceptance_ok:
        return build_check(
            key=f"{ruleset_id}_closure",
            abs_ids=[abs_id],
            label=f"{upper} closure",
            path=acceptance_path,
            ok=True,
            detail=acceptance_detail,
        )
    retirement_ok, retirement_detail = validate_claim_retirement_receipt(retirement or {}, ruleset=upper)
    if retirement_ok:
        return build_check(
            key=f"{ruleset_id}_closure",
            abs_ids=[abs_id],
            label=f"{upper} closure",
            path=retirement_path,
            ok=True,
            detail=retirement_detail,
        )
    return build_check(
        key=f"{ruleset_id}_closure",
        abs_ids=[abs_id],
        label=f"{upper} closure",
        path=acceptance_path,
        ok=False,
        detail=f"need {upper}_ACCEPTANCE_PROOF.generated.json or {upper}_CLAIM_RETIREMENT.generated.json",
    )


def main() -> int:
    checks: list[dict[str, Any]] = [
        receipt_check(
            key="canonical_domain_policy",
            abs_ids=["ABS-016"],
            label="Canonical domain policy",
            path=RUN_SERVICES_ROOT / ".codex-studio" / "published" / "CANONICAL_DOMAIN_POLICY.generated.json",
            validator=validate_canonical_domain,
        ),
        receipt_check(
            key="live_route_proof",
            abs_ids=["ABS-004", "ABS-016"],
            label="Live public route proof",
            path=RUN_SERVICES_ROOT / ".codex-studio" / "published" / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json",
            validator=validate_live_route_proof,
        ),
        receipt_check(
            key="live_support_flow",
            abs_ids=["ABS-017"],
            label="Live support/contact proof",
            path=RUN_SERVICES_ROOT / ".codex-studio" / "published" / "SUPPORT_CASE_FLOW_PROOF.generated.json",
            validator=validate_live_support_proof,
        ),
        receipt_check(
            key="live_oauth_linking",
            abs_ids=["ABS-005"],
            label="Live Google OAuth/account-linking proof",
            path=RUN_SERVICES_ROOT / ".codex-studio" / "published" / "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
            validator=validate_live_oauth_linking_proof,
        ),
        receipt_check(
            key="desktop_execution_proof",
            abs_ids=["ABS-001", "ABS-018"],
            label="Fresh desktop execution proof",
            path=PRESENTATION_ROOT / ".codex-studio" / "published" / "CHUMMER5A_DESKTOP_EXECUTION_PROOF.generated.json",
            validator=validate_desktop_execution_proof,
        ),
        receipt_check(
            key="human_parity_matrix",
            abs_ids=["ABS-001"],
            label="Human parity matrix proof",
            path=PRESENTATION_ROOT / ".codex-studio" / "published" / "CHUMMER5A_HUMAN_PARITY_MATRIX_PROOF.generated.json",
            validator=validate_human_parity,
        ),
        receipt_check(
            key="portable_receipts_audit",
            abs_ids=["ABS-012"],
            label="Portable receipts audit",
            path=RUN_SERVICES_ROOT / ".codex-studio" / "published" / "PORTABLE_RECEIPTS_AUDIT.generated.json",
            validator=validate_portable_receipts_audit,
        ),
        receipt_check(
            key="public_claim_scan",
            abs_ids=["ABS-015"],
            label="Public claim scan",
            path=RUN_SERVICES_ROOT / ".codex-studio" / "published" / "PUBLIC_CLAIM_SCAN.generated.json",
            validator=validate_pass,
        ),
        validate_sr5_closure(),
        validate_ruleset_decision(ruleset_id="sr4", abs_id="ABS-003"),
        validate_ruleset_decision(ruleset_id="sr6", abs_id="ABS-002"),
    ]

    pending_abs_ids: list[str] = []
    pending_checks: list[dict[str, Any]] = []
    for check in checks:
        if not check["ok"]:
            pending_checks.append(check)
            for abs_id in check["abs_ids"]:
                if abs_id not in pending_abs_ids:
                    pending_abs_ids.append(abs_id)

    payload = {
        "generated_at": now_iso(),
        "closure_done": not pending_checks,
        "pending_abs_ids": pending_abs_ids,
        "pending_check_keys": [check["key"] for check in pending_checks],
        "checks": checks,
        "summary": (
            "Absolute audit closure gate is green."
            if not pending_checks
            else "Absolute audit closure gate is still open."
        ),
    }
    print(json.dumps(payload, indent=2))
    return 0 if not pending_checks else 1


if __name__ == "__main__":
    raise SystemExit(main())
