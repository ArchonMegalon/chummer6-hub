#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import yaml
import re


RUN_SERVICES_ROOT = Path("/docker/chummercomplete/chummer.run-services")
PRESENTATION_ROOT = Path("/docker/chummercomplete/chummer-presentation")
CORE_ROOT = Path("/docker/chummercomplete/chummer-core-engine")
PASS_STATUSES = {"pass", "passed", "ready", "ok", "green"}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
EXPECTED_CODEX_REDIRECT = "/auth/google/start?next=%2Fparticipate%2Fcodex"
LIVE_BASE_URL = "https://chummer.run"


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


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


def status_is_pass(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    return str(payload.get("status") or "").strip().lower() in PASS_STATUSES


def rel(path: Path) -> str:
    return str(path)


def resolve_path(root: Path, candidate: Any) -> Path | None:
    if not isinstance(candidate, str):
        return None
    text = candidate.strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else root / path


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


def run_command(command: list[str], *, cwd: Path, env_additions: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = None
    if env_additions:
        env = {**os.environ, **env_additions}
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def fetch_no_redirect(url: str) -> tuple[int | None, str | None]:
    opener = build_opener(NoRedirectHandler())
    request = Request(url, headers={"User-Agent": "codexliz-audit/1.0"})
    try:
        with opener.open(request, timeout=20) as response:
            return response.getcode(), response.headers.get("Location")
    except HTTPError as exc:
        return exc.code, exc.headers.get("Location")
    except Exception:
        return None, None


def load_manifest_routes() -> list[dict[str, Any]]:
    manifest_path = RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_LANDING_MANIFEST.yaml"
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    routes: list[dict[str, Any]] = []
    for key in ("public_routes", "auth_routes", "registered_routes"):
        values = payload.get(key) or []
        if isinstance(values, list):
            routes.extend(item for item in values if isinstance(item, dict))
    return routes


def find_manifest_route(path_value: str) -> dict[str, Any] | None:
    for route in load_manifest_routes():
        if str(route.get("path") or "").strip() == path_value:
            return route
    return None


def validate_canonical_domain() -> dict[str, Any]:
    path = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "CANONICAL_DOMAIN_POLICY.generated.json"
    payload = load_json(path)
    route = find_manifest_route("/participate/codex")
    route_required = isinstance(route, dict) and bool(route.get("must_exist")) is True
    canonical = payload.get("canonical_public_domain") if payload else None
    status = str(payload.get("status") or "").strip().lower() if payload else "missing"
    alias_state = (payload.get("domain_status") or {}).get("chummer6.run") if payload else None
    ok = status in PASS_STATUSES and canonical == "chummer.run" and alias_state == "not_used" and route_required
    return build_check(
        key="canonical_domain_policy",
        abs_ids=["ABS-016"],
        label="Canonical domain policy",
        path=path,
        ok=ok,
        detail=(
            f"status={status or 'missing'} canonical_public_domain={canonical!r} "
            f"chummer6.run={alias_state!r} participate_codex_required={route_required}"
        ),
    )


def validate_live_route_proof() -> dict[str, Any]:
    path = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"
    payload = load_json(path) or {}
    summary = payload.get("summary") or {}
    routes = payload.get("routes") or []
    failed_count = summary.get("failed_count")
    route_count = summary.get("route_count")
    expected_route_count = len(load_manifest_routes())
    codex_route = None
    if isinstance(routes, list):
        for route in routes:
            if isinstance(route, dict) and route.get("path") == "/participate/codex":
                codex_route = route
                break
    live_status, live_location = fetch_no_redirect(f"{LIVE_BASE_URL}/participate/codex")
    proof_redirect = codex_route.get("redirect_location") if isinstance(codex_route, dict) else None
    proof_success = bool(codex_route.get("success")) if isinstance(codex_route, dict) else False
    # For /participate/codex, accept either:
    # 1. proof redirect matches expected OAuth path, OR
    # 2. live redirect is correct (proof may be stale)
    redirect_ok = (
        isinstance(codex_route, dict)
        and (
            (proof_success and proof_redirect == EXPECTED_CODEX_REDIRECT)
            or (live_status in REDIRECT_STATUSES and live_location == EXPECTED_CODEX_REDIRECT)
        )
    )
    
    ok = (
        isinstance(route_count, int)
        and route_count >= expected_route_count
        and isinstance(failed_count, int)
        and failed_count == 0
        and redirect_ok
        and isinstance(live_status, int)
        and live_status in REDIRECT_STATUSES
        and live_location == EXPECTED_CODEX_REDIRECT
    )
    return build_check(
        key="live_route_proof",
        abs_ids=["ABS-004", "ABS-016"],
        label="Live public route proof",
        path=path,
        ok=ok,
        detail=(
            f"route_count={route_count} expected_route_count={expected_route_count} failed_count={failed_count} "
            f"proof_has_participate_codex={isinstance(codex_route, dict)} proof_success={proof_success} "
            f"proof_redirect={proof_redirect!r} live_status={live_status!r} live_location={live_location!r}"
        ),
    )


def validate_live_support_flow() -> dict[str, Any]:
    path = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "SUPPORT_CASE_FLOW_PROOF.generated.json"
    result = run_command(
        ["python3", "scripts/check-support-case-flow.py"],
        cwd=RUN_SERVICES_ROOT,
        env_additions={"CHUMMER_HUB_PLAYWRIGHT_BASE_URL": LIVE_BASE_URL},
    )
    ok = result.returncode == 0
    return build_check(
        key="live_support_flow",
        abs_ids=["ABS-017"],
        label="Live support/contact proof",
        path=path,
        ok=ok,
        detail=f"exit_code={result.returncode} stdout={result.stdout.strip()!r} stderr={result.stderr.strip()!r}",
    )


def validate_live_oauth_linking() -> dict[str, Any]:
    path = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    script_path = RUN_SERVICES_ROOT / "scripts" / "check-google-oauth-linking.py"
    source = script_path.read_text(encoding="utf-8") if script_path.is_file() else ""
    required_tokens = [
        "requests.Session",
        "allow_redirects=False",
        "/auth/google/start",
        "/account/access",
        "Location",
    ]
    source_ok = all(token in source for token in required_tokens)
    result = run_command(["python3", str(script_path)], cwd=RUN_SERVICES_ROOT) if script_path.is_file() else None
    ok = script_path.is_file() and source_ok and result is not None and result.returncode == 0
    return build_check(
        key="live_oauth_linking",
        abs_ids=["ABS-005"],
        label="Live Google OAuth/account-linking proof",
        path=path,
        ok=ok,
        detail=(
            f"script_exists={script_path.is_file()} source_ok={source_ok} "
            f"exit_code={(result.returncode if result is not None else 'missing')} "
            f"stdout={(result.stdout.strip() if result is not None else '')!r}"
        ),
    )


def validate_desktop_execution_proof() -> dict[str, Any]:
    path = PRESENTATION_ROOT / ".codex-studio" / "published" / "CHUMMER5A_DESKTOP_EXECUTION_PROOF.generated.json"
    payload = load_json(path)
    receipts = payload.get("receipts") if payload else None
    required = {
        "screenshot_review": PRESENTATION_ROOT / ".codex-studio" / "published" / "CHUMMER5A_SCREENSHOT_REVIEW_GATE.generated.json",
        "workflow_execution": PRESENTATION_ROOT / ".codex-studio" / "published" / "DESKTOP_WORKFLOW_EXECUTION_GATE.generated.json",
        "visual_familiarity": PRESENTATION_ROOT / ".codex-studio" / "published" / "DESKTOP_VISUAL_FAMILIARITY_EXIT_GATE.generated.json",
        "human_parity_matrix": PRESENTATION_ROOT / ".codex-studio" / "published" / "CHUMMER5A_HUMAN_PARITY_MATRIX_PROOF.generated.json",
    }
    receipts_ok = isinstance(receipts, dict)
    if receipts_ok:
        for key, expected_path in required.items():
            candidate = resolve_path(PRESENTATION_ROOT, receipts.get(key))
            if candidate is None or candidate != expected_path or not expected_path.is_file():
                receipts_ok = False
                break
    ok = status_is_pass(payload) and receipts_ok
    return build_check(
        key="desktop_execution_proof",
        abs_ids=["ABS-001", "ABS-018"],
        label="Fresh desktop execution proof",
        path=path,
        ok=ok,
        detail=f"status={payload.get('status')!r} receipts_bound={receipts_ok}" if payload else "missing receipt",
    )


def validate_human_parity() -> dict[str, Any]:
    path = PRESENTATION_ROOT / ".codex-studio" / "published" / "CHUMMER5A_HUMAN_PARITY_MATRIX_PROOF.generated.json"
    payload = load_json(path)
    matrix = payload.get("matrix") if payload else {}
    row_count = matrix.get("row_count") if isinstance(matrix, dict) else None
    family_count = matrix.get("family_count") if isinstance(matrix, dict) else None
    ok = status_is_pass(payload) and isinstance(row_count, int) and row_count > 0 and isinstance(family_count, int) and family_count > 0
    return build_check(
        key="human_parity_matrix",
        abs_ids=["ABS-001"],
        label="Human parity matrix proof",
        path=path,
        ok=ok,
        detail=f"status={payload.get('status')!r} row_count={row_count} family_count={family_count}" if payload else "missing receipt",
    )


def validate_portable_receipts_audit() -> dict[str, Any]:
    path = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "PORTABLE_RECEIPTS_AUDIT.generated.json"
    roots = [
        RUN_SERVICES_ROOT / ".codex-studio" / "published",
        PRESENTATION_ROOT / ".codex-studio" / "published",
        CORE_ROOT / ".codex-studio" / "published",
    ]
    scanned = 0
    machine_specific_hits: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        for candidate in root.glob("*.json"):
            scanned += 1
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8", errors="ignore"))
                found_home_path = False

                def walk(node: Any) -> bool:
                    if isinstance(node, dict):
                        for value in node.values():
                            if walk(value):
                                return True
                        return False
                    if isinstance(node, list):
                        for item in node:
                            if walk(item):
                                return True
                        return False
                    if isinstance(node, str):
                        return re.search(r"/home/[^/\s\"']+/", node) is not None
                    return False

                if walk(payload):
                    machine_specific_hits.append(str(candidate))
            except Exception:
                machine_specific_hits.append(str(candidate))
    ok = scanned > 0 and not machine_specific_hits
    return build_check(
        key="portable_receipts_audit",
        abs_ids=["ABS-012"],
        label="Portable receipts audit",
        path=path,
        ok=ok,
        detail=f"scanned_artifact_count={scanned} machine_specific_hits={len(machine_specific_hits)}",
    )


def validate_public_claim_scan() -> dict[str, Any]:
    path = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "PUBLIC_CLAIM_SCAN.generated.json"
    payload = load_json(path)
    ok = status_is_pass(payload)
    return build_check(
        key="public_claim_scan",
        abs_ids=["ABS-015"],
        label="Public claim scan",
        path=path,
        ok=ok,
        detail=f"status={payload.get('status')!r}" if payload else "missing receipt",
    )


def validate_sr5_closure() -> dict[str, Any]:
    path = CORE_ROOT / ".codex-studio" / "published" / "SR5_ACCEPTANCE_PROOF.generated.json"
    payload = load_json(path)
    evidence = payload.get("evidence_receipts") if payload else None
    evidence_ok = isinstance(evidence, list) and len(evidence) >= 2
    if evidence_ok:
        for item in evidence:
            candidate = resolve_path(CORE_ROOT, item)
            if candidate is None or not candidate.is_file():
                evidence_ok = False
                break
    workflows = payload.get("accepted_workflows") if payload else None
    ok = (
        status_is_pass(payload)
        and payload.get("ruleset") == "SR5"
        and payload.get("serious_implementation_claim") == "allowed"
        and payload.get("coverage_threshold") == "production_grade"
        and isinstance(workflows, list)
        and len(workflows) >= 5
        and evidence_ok
    )
    return build_check(
        key="sr5_closure",
        abs_ids=["ABS-006"],
        label="SR5 closure",
        path=path,
        ok=ok,
        detail=(
            f"status={payload.get('status')!r} ruleset={payload.get('ruleset')!r} "
            f"serious_implementation_claim={payload.get('serious_implementation_claim')!r} "
            f"coverage_threshold={payload.get('coverage_threshold')!r} "
            f"accepted_workflows={len(workflows) if isinstance(workflows, list) else 'missing'} "
            f"evidence_receipts={len(evidence) if isinstance(evidence, list) else 'missing'}"
        ) if payload else "missing receipt",
    )


def validate_claim_retirement(ruleset: str, abs_id: str) -> dict[str, Any]:
    path = CORE_ROOT / ".codex-studio" / "published" / f"{ruleset}_CLAIM_RETIREMENT.generated.json"
    payload = load_json(path)
    claim_status = str(payload.get("claim_status") or "").strip().lower() if payload else "missing"
    ok = status_is_pass(payload) and payload.get("ruleset") == ruleset and claim_status in {"retired", "not_supported", "disallowed"}
    return build_check(
        key=f"{ruleset.lower()}_closure",
        abs_ids=[abs_id],
        label=f"{ruleset} closure",
        path=path,
        ok=ok,
        detail=f"status={payload.get('status')!r} ruleset={payload.get('ruleset')!r} claim_status={claim_status}" if payload else "missing receipt",
    )


def main() -> int:
    checks = [
        validate_canonical_domain(),
        validate_live_route_proof(),
        validate_live_support_flow(),
        validate_live_oauth_linking(),
        validate_desktop_execution_proof(),
        validate_human_parity(),
        validate_portable_receipts_audit(),
        validate_public_claim_scan(),
        validate_sr5_closure(),
        validate_claim_retirement("SR4", "ABS-003"),
        validate_claim_retirement("SR6", "ABS-002"),
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
        "summary": "Absolute audit substance gate is green." if not pending_checks else "Absolute audit substance gate is still open.",
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if not pending_checks else 1


if __name__ == "__main__":
    raise SystemExit(main())
