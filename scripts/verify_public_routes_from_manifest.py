#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_MANIFEST = REPO_ROOT / ".codex-design" / "product" / "PUBLIC_LANDING_MANIFEST.yaml"
DEFAULT_OUTPUT = REPO_ROOT / ".codex-studio" / "published" / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
AUTH_OPERATION_OK_STATUSES = {200, 302, 303, 307, 308, 400, 405}
CONTROLLER_CONTRACT_OK_STATUSES = {200, 302, 303, 307, 308, 400, 404, 405}
PLACEHOLDER_SAMPLE_LOOKUP = {
    "case": "sample-case-id",
    "caseid": "sample-case-id",
    "case_id": "sample-case-id",
    "submission": "sample-submission-id",
    "submissionid": "sample-submission-id",
    "submission_id": "sample-submission-id",
}
ROUTE_LIST_KEYS = ("public_routes", "auth_routes", "registered_routes")


@dataclass
class RouteResult:
    path: str
    audience: str
    purpose: str
    requires_auth: bool
    must_exist: bool
    guest_fallback: str | None
    mode: str
    success: bool
    status_code: int | None = None
    final_url: str | None = None
    redirect_location: str | None = None
    expectation: str | None = None
    detail: str | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify public, auth, and registered Chummer routes from PUBLIC_LANDING_MANIFEST.yaml.")
    parser.add_argument("--base-url", required=True, help="Base URL to verify, for example https://chummer.run")
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Path to PUBLIC_LANDING_MANIFEST.yaml")
    parser.add_argument(
        "--output",
        default="",
        help="Optional path for the machine-readable JSON proof packet")
    parser.add_argument("--public-host", default="", help="Optional Host header override")
    parser.add_argument("--forwarded-proto", default="", help="Optional X-Forwarded-Proto override")
    return parser.parse_args(argv)


def load_hub_live_audit_module() -> Any:
    audit_script = SCRIPT_DIR / "hub-live-audit.py"
    spec = importlib.util.spec_from_file_location("hub_live_audit_helper", audit_script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load shared fetch helper from {audit_script}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def normalize_target(target: str | None) -> tuple[str, tuple[tuple[str, str], ...], str]:
    if not target:
        return "", (), ""

    parsed = urlparse(target)
    path = parsed.path or "/"
    query_items = tuple(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    fragment = parsed.fragment or ""
    return path, query_items, fragment


def _normalize_placeholder_token(token: str) -> str:
    return "".join(ch for ch in token.lower() if ch.isalnum())


def resolve_route_path_placeholders(route_path: str) -> str:
    def replace_token(match: re.Match[str]) -> str:
        token = _normalize_placeholder_token(match.group(1))
        return PLACEHOLDER_SAMPLE_LOOKUP.get(token, f"sample-{token}")

    return re.sub(r"\{([^{}]+)\}", replace_token, route_path)


def read_manifest(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} did not load into a YAML object")

    normalized: list[dict[str, Any]] = []
    for key in ROUTE_LIST_KEYS:
        routes = payload.get(key) or []
        if not isinstance(routes, list):
            raise AssertionError(f"{path} {key} is not a list")
        for index, item in enumerate(routes):
            if not isinstance(item, dict):
                raise AssertionError(f"{path} {key}[{index}] is not an object")
            route_path = str(item.get("path") or "").strip()
            if not route_path.startswith("/"):
                raise AssertionError(f"{path} {key}[{index}] has invalid path {route_path!r}")
            normalized.append(item)

    if not normalized:
        raise AssertionError(f"{path} did not contain any route lists in {ROUTE_LIST_KEYS}")

    return payload, normalized


def resolve_repo_path(path_value: str) -> Path:
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def verify_route(fetch, base_url: str, route: dict[str, Any], *, public_host: str | None, forwarded_proto: str | None) -> RouteResult:
    path = str(route.get("path") or "")
    audience = str(route.get("audience") or "")
    purpose = str(route.get("purpose") or "")
    requires_auth = bool(route.get("requires_auth"))
    must_exist = bool(route.get("must_exist"))
    guest_fallback = str(route.get("guest_fallback") or "") or None
    request_path = str(route.get("verification_path") or path)
    resolved_request_path = resolve_route_path_placeholders(request_path)
    verification_mode = str(route.get("verification_mode") or "").strip()

    if verification_mode:
        if verification_mode != "controller_contract":
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=verification_mode,
                success=False,
                expectation="recognized verification_mode",
                detail=f"unsupported verification_mode {verification_mode!r}")

        verification_file_value = str(route.get("verification_file") or "").strip()
        verification_pattern = str(route.get("verification_pattern") or "")
        expectation = f"controller contract contains {verification_pattern}"
        if not verification_file_value or not verification_pattern:
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=verification_mode,
                success=False,
                expectation=expectation,
                detail="controller_contract verification requires verification_file and verification_pattern")

        verification_file = resolve_repo_path(verification_file_value)
        try:
            source = verification_file.read_text(encoding="utf-8")
        except Exception as exc:
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=verification_mode,
                success=False,
                expectation=expectation,
                detail=f"could not read {verification_file}: {exc}")

        if not verification_pattern in source:
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=verification_mode,
                success=False,
                status_code=None,
                final_url=None,
                expectation=expectation,
                detail=f"expected {verification_pattern} in {verification_file}")

        expectation = f"{expectation} and resolves {resolved_request_path}"
        try:
            status, _, headers, final_url = fetch(
                base_url,
                resolved_request_path,
                public_host=public_host or None,
                forwarded_proto=forwarded_proto or None,
                follow_redirects=True)
            redirect_location = headers.get("location")
            success = status in CONTROLLER_CONTRACT_OK_STATUSES
            detail = (
                f"expected {verification_pattern} in {verification_file} and "
                f"{resolved_request_path} to resolve one of {sorted(CONTROLLER_CONTRACT_OK_STATUSES)}, got {status}"
            )
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=verification_mode,
                success=success,
                status_code=status,
                final_url=final_url,
                redirect_location=redirect_location,
                expectation=expectation,
                detail=detail)
        except Exception as exc:
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=verification_mode,
                success=False,
                expectation=expectation,
                detail=f"could not resolve {resolved_request_path}: {exc}")

    if requires_auth:
        mode = "registered_fallback"
        expectation = f"anonymous request redirects to {guest_fallback}"
        try:
            status, _, headers, final_url = fetch(
                base_url,
            resolved_request_path,
            public_host=public_host or None,
            forwarded_proto=forwarded_proto or None,
            follow_redirects=False)
            redirect_location = headers.get("location")
            success = status in REDIRECT_STATUSES and normalize_target(redirect_location) == normalize_target(guest_fallback)
            detail = (
                f"expected anonymous redirect to {guest_fallback}, got {redirect_location or '<none>'} "
                f"(status {status})")
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=mode,
                success=success,
                status_code=status,
                final_url=final_url,
                redirect_location=redirect_location,
                expectation=expectation,
                detail=detail)
        except Exception as exc:
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=mode,
                success=False,
                expectation=expectation,
                detail=f"request failed: {exc}")

    if purpose == "auth_operation":
        mode = "auth_operation"
        expectation = f"auth operation returns one of {sorted(AUTH_OPERATION_OK_STATUSES)} without a 5xx"
        try:
            status, _, headers, final_url = fetch(
                base_url,
            resolved_request_path,
            public_host=public_host or None,
            forwarded_proto=forwarded_proto or None,
            follow_redirects=False)
            redirect_location = headers.get("location")
            success = status in AUTH_OPERATION_OK_STATUSES
            detail = f"expected auth-operation status in {sorted(AUTH_OPERATION_OK_STATUSES)}, got {status}"
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=mode,
                success=success,
                status_code=status,
                final_url=final_url,
                redirect_location=redirect_location,
                expectation=expectation,
                detail=detail)
        except Exception as exc:
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=mode,
                success=False,
                expectation=expectation,
                detail=f"request failed: {exc}")

    mode = "public_route"
    expectation = "public route resolves successfully"
    try:
        status, _, headers, final_url = fetch(
            base_url,
            resolved_request_path,
            public_host=public_host or None,
            forwarded_proto=forwarded_proto or None,
            follow_redirects=True)
        redirect_location = headers.get("location")
        success = status == 200
        detail = f"expected 200 from public route, got {status}"
        return RouteResult(
            path=path,
            audience=audience,
            purpose=purpose,
            requires_auth=requires_auth,
            must_exist=must_exist,
            guest_fallback=guest_fallback,
            mode=mode,
            success=success,
            status_code=status,
            final_url=final_url,
            redirect_location=redirect_location,
            expectation=expectation,
            detail=detail)
    except Exception as exc:
        return RouteResult(
            path=path,
            audience=audience,
            purpose=purpose,
            requires_auth=requires_auth,
            must_exist=must_exist,
            guest_fallback=guest_fallback,
            mode=mode,
            success=False,
            expectation=expectation,
            detail=f"request failed: {exc}")


def manifest_path_label(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def build_report(manifest: dict[str, Any], manifest_path: Path, args: argparse.Namespace, routes: list[RouteResult]) -> dict[str, Any]:
    passed = [route for route in routes if route.success]
    failed = [route for route in routes if not route.success]
    registered = [route for route in routes if route.requires_auth]
    auth_operations = [route for route in routes if route.mode == "auth_operation"]
    public = [route for route in routes if route.mode == "public_route"]
    controller_contracts = [route for route in routes if route.mode == "controller_contract"]

    return {
        "contract_name": "chummer.public_route_proof",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "base_url": args.base_url,
        "public_host": args.public_host or None,
        "forwarded_proto": args.forwarded_proto or None,
        "manifest_path": manifest_path_label(manifest_path),
        "manifest_surface": manifest.get("surface"),
        "manifest_version": manifest.get("version"),
        "summary": {
            "route_count": len(routes),
            "passed_count": len(passed),
            "failed_count": len(failed),
            "public_route_count": len(public),
            "auth_operation_count": len(auth_operations),
            "registered_route_count": len(registered),
            "controller_contract_count": len(controller_contracts),
            "failed_paths": [route.path for route in failed],
        },
        "routes": [asdict(route) for route in routes],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest_path = Path(args.manifest).resolve()
    manifest, manifest_routes = read_manifest(manifest_path)
    hub_live_audit = load_hub_live_audit_module()

    results = [
        verify_route(
            hub_live_audit.fetch,
            args.base_url,
            route,
            public_host=args.public_host,
            forwarded_proto=args.forwarded_proto)
        for route in manifest_routes
        if bool(route.get("must_exist", True))
    ]
    report = build_report(manifest, manifest_path, args, results)
    report_text = json.dumps(report, indent=2) + "\n"

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_text, encoding="utf-8")

    sys.stdout.write(report_text)
    return 1 if report["summary"]["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
