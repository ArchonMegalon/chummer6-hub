#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, replace
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
CONTROLLER_CONTRACT_OK_STATUSES = {200, 301, 302, 303, 307, 308}
PLACEHOLDER_SAMPLE_LOOKUP = {
    "case": "sample-case-id",
    "caseid": "sample-case-id",
    "case_id": "sample-case-id",
    "package": "desktop-preview",
    "packageid": "desktop-preview",
    "package_id": "desktop-preview",
    "submission": "sample-submission-id",
    "submissionid": "sample-submission-id",
    "submission_id": "sample-submission-id",
}
ROUTE_LIST_KEYS = ("public_routes", "auth_routes", "registered_routes")
DEFAULT_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("CHUMMER_PUBLIC_ROUTE_PROOF_REQUEST_TIMEOUT_SECONDS", "8"))
DEFAULT_MAX_RETRIES = int(os.environ.get("CHUMMER_PUBLIC_ROUTE_PROOF_MAX_RETRIES", "1"))
DEFAULT_RETRY_DELAY_SECONDS = float(os.environ.get("CHUMMER_PUBLIC_ROUTE_PROOF_RETRY_DELAY_SECONDS", "0.5"))
DEFAULT_MAX_WORKERS = int(os.environ.get("CHUMMER_PUBLIC_ROUTE_PROOF_MAX_WORKERS", "12"))
DEFAULT_TIMEOUT_RECOVERY_SECONDS = float(os.environ.get("CHUMMER_PUBLIC_ROUTE_PROOF_TIMEOUT_RECOVERY_SECONDS", "30"))
DEFAULT_TIMEOUT_RECOVERY_RETRIES = int(os.environ.get("CHUMMER_PUBLIC_ROUTE_PROOF_TIMEOUT_RECOVERY_RETRIES", "1"))
TIMEOUT_FAILURE_TOKENS = ("timed out", "timeout", "read operation timed out")


@dataclass
class RouteResult:
    path: str
    audience: str
    purpose: str
    requires_auth: bool
    must_exist: bool
    guest_fallback: str | None
    mode: str
    proof_class: str
    positive_proof: bool
    seeded_receipt: bool
    success: bool
    status_code: int | None = None
    final_url: str | None = None
    redirect_location: str | None = None
    expectation: str | None = None
    detail: str | None = None
    response_sha256: str | None = None
    text_excerpt: str | None = None
    critical_excerpt: str | None = None
    cache_control: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    detection_hits: list[str] | None = None


@dataclass
class NegativePathResult:
    path: str
    sample_path: str
    expectation: str
    success: bool
    positive_proof: bool
    status_code: int | None = None
    final_url: str | None = None
    detail: str | None = None


PROOF_TOKENS = (
    "load demo runner",
    "demo runner",
    "missing or stale",
    "not yet gold-ready",
    "review is required",
    "preview publication",
)


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
    parser.add_argument(
        "--strict-positive",
        action="store_true",
        help="Require live positive proof for parameterized controller-contract receipt routes instead of counting controller mapping alone.")
    parser.add_argument(
        "--seed-receipts",
        action="store_true",
        help="Allow seeded sample receipt routes to satisfy strict positive proof for parameterized receipt pages.")
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
        help="Per-request timeout when probing live public routes.")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Maximum retry count forwarded to the shared live fetch helper.")
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=DEFAULT_RETRY_DELAY_SECONDS,
        help="Base retry delay forwarded to the shared live fetch helper.")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="Maximum worker count for parallel live route verification.")
    parser.add_argument(
        "--disable-timeout-recovery",
        action="store_true",
        help="Disable isolated single-route retry for transport timeout failures.")
    parser.add_argument(
        "--timeout-recovery-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_RECOVERY_SECONDS,
        help="Per-request timeout for isolated timeout recovery retries.")
    parser.add_argument(
        "--timeout-recovery-retries",
        type=int,
        default=DEFAULT_TIMEOUT_RECOVERY_RETRIES,
        help="Retry count for isolated timeout recovery retries.")
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


def base_url_is_local(base_url: str) -> bool:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").strip().lower()
    return host in LOCAL_BASE_HOSTS


def base_url_is_canonical_public_host(base_url: str) -> bool:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").strip().lower()
    return host in CANONICAL_PUBLIC_ROUTE_PROOF_HOSTS


def resolve_effective_max_workers(base_url: str, requested_max_workers: int) -> int:
    if requested_max_workers <= 0:
        raise SystemExit("--max-workers must be positive")

    if base_url_is_local(base_url):
        return max(1, min(requested_max_workers, LOCAL_BASE_MAX_WORKERS))
    if base_url_is_canonical_public_host(base_url):
        return max(1, min(requested_max_workers, CANONICAL_PUBLIC_ROUTE_PROOF_MAX_WORKERS))

    return requested_max_workers


def resolve_effective_request_timeout_seconds(base_url: str, requested_timeout_seconds: float) -> float:
    if requested_timeout_seconds <= 0:
        raise SystemExit("--request-timeout-seconds must be positive")

    if base_url_is_local(base_url):
        return max(requested_timeout_seconds, LOCAL_BASE_REQUEST_TIMEOUT_SECONDS)
    if base_url_is_canonical_public_host(base_url):
        return max(requested_timeout_seconds, CANONICAL_PUBLIC_ROUTE_PROOF_REQUEST_TIMEOUT_SECONDS)

    return requested_timeout_seconds


def _normalize_placeholder_token(token: str) -> str:
    return "".join(ch for ch in token.lower() if ch.isalnum())


def resolve_route_path_placeholders(route_path: str) -> str:
    def replace_token(match: re.Match[str]) -> str:
        token = _normalize_placeholder_token(match.group(1))
        return PLACEHOLDER_SAMPLE_LOOKUP.get(token, f"sample-{token}")

    return re.sub(r"\{([^{}]+)\}", replace_token, route_path)


def resolve_negative_route_path_placeholders(route_path: str) -> str:
    def replace_token(match: re.Match[str]) -> str:
        token = _normalize_placeholder_token(match.group(1))
        return f"missing-{token or 'sample'}"

    return re.sub(r"\{([^{}]+)\}", replace_token, route_path)


def route_path_contains_placeholders(route_path: str) -> bool:
    return "{" in route_path and "}" in route_path


def _origin_tuple(value: str) -> tuple[str, str, int | None] | None:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        return None
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, host, port


def redirect_location_matches_exact_alias_contract(
    base_url: str,
    location: str | None,
    expected_path: str,
) -> bool:
    location_text = str(location or "").strip()
    if not location_text or not expected_path.startswith("/"):
        return False
    try:
        parsed = urlparse(location_text)
    except ValueError:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.path != expected_path:
        return False
    # A query delimiter is forbidden even when its value is empty.
    if "?" in location_text.split("#", 1)[0] or parsed.query:
        return False
    # The explicit empty fragment prevents user agents from inheriting a private
    # fragment from the alias request. Missing or non-empty fragments are unsafe.
    if "#" not in location_text or parsed.fragment:
        return False

    if parsed.scheme or parsed.netloc:
        if not parsed.scheme or not parsed.netloc:
            return False
        return _origin_tuple(base_url) == _origin_tuple(location_text)

    # Only a canonical root-relative reference is accepted for a relative target.
    return location_text.startswith("/") and not location_text.startswith("//")


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


def filter_manifest_routes(routes: list[dict[str, Any]], path_filters: list[str]) -> list[dict[str, Any]]:
    normalized_filters = [item.strip() for item in path_filters if item.strip()]
    if not normalized_filters:
        return routes

    allowed = set(normalized_filters)
    filtered = [route for route in routes if str(route.get("path") or "").strip() in allowed]
    if filtered:
        return filtered

    raise SystemExit(
        "--path did not match any manifest route: "
        + ", ".join(sorted(allowed))
    )


def resolve_repo_path(path_value: str) -> Path:
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def build_body_evidence(body_text: str, headers: dict[str, str]) -> dict[str, Any]:
    lowered = body_text.lower()
    detection_hits = [token for token in PROOF_TOKENS if token in lowered]
    first_hit_index = min((lowered.find(token) for token in detection_hits), default=-1)
    critical_excerpt = None
    if first_hit_index >= 0:
        start = max(0, first_hit_index - 120)
        end = min(len(body_text), first_hit_index + 160)
        critical_excerpt = " ".join(body_text[start:end].split())[:280]
    return {
        "response_sha256": hashlib.sha256(body_text.encode("utf-8")).hexdigest(),
        "text_excerpt": " ".join(body_text.split())[:280],
        "critical_excerpt": critical_excerpt,
        "cache_control": headers.get("cache-control"),
        "etag": headers.get("etag"),
        "last_modified": headers.get("last-modified"),
        "detection_hits": detection_hits,
    }


def verify_route(
    fetch,
    base_url: str,
    route: dict[str, Any],
    *,
    public_host: str | None,
    forwarded_proto: str | None,
    strict_positive: bool,
    seed_receipts: bool,
    request_timeout_seconds: float,
    max_retries: int,
    retry_delay_seconds: float,
) -> RouteResult:
    path = str(route.get("path") or "")
    audience = str(route.get("audience") or "")
    purpose = str(route.get("purpose") or "")
    requires_auth = bool(route.get("requires_auth"))
    must_exist = bool(route.get("must_exist"))
    guest_fallback = str(route.get("guest_fallback") or "") or None
    request_path = str(route.get("verification_path") or path)
    resolved_request_path = resolve_route_path_placeholders(request_path)
    resolved_guest_fallback = resolve_route_path_placeholders(guest_fallback) if guest_fallback else None
    required_texts = tuple(
        str(item).strip()
        for item in (route.get("required_texts") or [])
        if str(item).strip()
    )
    required_final_url_prefix = str(route.get("required_final_url_prefix") or "").strip()
    required_redirect_location_prefix = str(route.get("required_redirect_location_prefix") or "").strip()
    verification_mode = str(route.get("verification_mode") or "").strip()
    receipt_seed_required = verification_mode == "controller_contract" and route_path_contains_placeholders(request_path)

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
                proof_class="controller_contract",
                positive_proof=False,
                seeded_receipt=False,
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
                proof_class="controller_contract",
                positive_proof=False,
                seeded_receipt=False,
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
                proof_class="controller_contract",
                positive_proof=False,
                seeded_receipt=False,
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
                proof_class="controller_contract",
                positive_proof=False,
                seeded_receipt=False,
                success=False,
                status_code=None,
                final_url=None,
                expectation=expectation,
                detail=f"expected {verification_pattern} in {verification_file}")

        expectation = f"{expectation} and resolves {resolved_request_path}"
        if strict_positive and receipt_seed_required and not seed_receipts:
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=verification_mode,
                proof_class="seed_required",
                positive_proof=False,
                seeded_receipt=False,
                success=False,
                expectation=f"{expectation} with seeded receipt proof",
                detail="strict positive proof for parameterized receipt routes requires --seed-receipts")

        try:
            status, body_text, headers, final_url = fetch(
                base_url,
                resolved_request_path,
                public_host=public_host or None,
                forwarded_proto=forwarded_proto or None,
                follow_redirects=True,
                request_timeout_seconds=request_timeout_seconds,
                max_retries=max_retries,
                retry_delay_seconds=retry_delay_seconds)
            redirect_location = headers.get("location")
            positive_proof = status in CONTROLLER_CONTRACT_OK_STATUSES
            if strict_positive:
                success = positive_proof
                proof_class = "receipt_route" if success else "negative_path"
                detail = (
                    f"expected {verification_pattern} in {verification_file} and "
                    f"{resolved_request_path} to resolve one of {sorted(CONTROLLER_CONTRACT_OK_STATUSES)}, got {status}"
                )
            else:
                success = True
                proof_class = "controller_contract"
                detail = (
                    f"controller contract matched {verification_pattern} in {verification_file}; "
                    f"sample path {resolved_request_path} returned {status}, so this counts as controller-contract proof"
                    f"{' and positive route proof.' if positive_proof else ' only.'}"
                )
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=verification_mode,
                proof_class=proof_class,
                positive_proof=positive_proof,
                seeded_receipt=receipt_seed_required and seed_receipts,
                success=success,
                status_code=status,
                final_url=final_url,
                redirect_location=redirect_location,
                expectation=expectation,
                detail=detail,
                **build_body_evidence(body_text, headers))
        except Exception as exc:
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=verification_mode,
                proof_class="controller_contract" if not strict_positive else "negative_path",
                positive_proof=False,
                seeded_receipt=receipt_seed_required and seed_receipts,
                success=not strict_positive,
                expectation=expectation,
                detail=(
                    f"controller contract matched {verification_pattern} in {verification_file}, "
                    f"but sample path {resolved_request_path} could not be resolved: {exc}"
                    if not strict_positive
                    else f"could not resolve {resolved_request_path}: {exc}"
                ))

    if requires_auth:
        mode = "registered_fallback"
        expectation = f"anonymous request redirects to {resolved_guest_fallback}"
        try:
            status, body_text, headers, final_url = fetch(
                base_url,
                resolved_request_path,
                public_host=public_host or None,
                forwarded_proto=forwarded_proto or None,
                follow_redirects=False,
                request_timeout_seconds=request_timeout_seconds,
                max_retries=max_retries,
                retry_delay_seconds=retry_delay_seconds)
            redirect_location = headers.get("location")
            success = status in REDIRECT_STATUSES and normalize_target(redirect_location) == normalize_target(resolved_guest_fallback)
            detail = (
                f"expected anonymous redirect to {resolved_guest_fallback}, got {redirect_location or '<none>'} "
                f"(status {status})")
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=mode,
                proof_class=mode,
                positive_proof=success,
                seeded_receipt=False,
                success=success,
                status_code=status,
                final_url=final_url,
                redirect_location=redirect_location,
                expectation=expectation,
                detail=detail,
                **build_body_evidence(body_text, headers))
        except Exception as exc:
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=mode,
                proof_class=mode,
                positive_proof=False,
                seeded_receipt=False,
                success=False,
                expectation=expectation,
                detail=f"request failed: {exc}")

    if purpose == "auth_operation":
        mode = "auth_operation"
        expectation = f"auth operation returns one of {sorted(AUTH_OPERATION_OK_STATUSES)} without a 5xx"
        try:
            status, body_text, headers, final_url = fetch(
                base_url,
                resolved_request_path,
                public_host=public_host or None,
                forwarded_proto=forwarded_proto or None,
                follow_redirects=False,
                request_timeout_seconds=request_timeout_seconds,
                max_retries=max_retries,
                retry_delay_seconds=retry_delay_seconds)
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
                proof_class=mode,
                positive_proof=success,
                seeded_receipt=False,
                success=success,
                status_code=status,
                final_url=final_url,
                redirect_location=redirect_location,
                expectation=expectation,
                detail=detail,
                **build_body_evidence(body_text, headers))
        except Exception as exc:
            return RouteResult(
                path=path,
                audience=audience,
                purpose=purpose,
                requires_auth=requires_auth,
                must_exist=must_exist,
                guest_fallback=guest_fallback,
                mode=mode,
                proof_class=mode,
                positive_proof=False,
                seeded_receipt=False,
                success=False,
                expectation=expectation,
                detail=f"request failed: {exc}")

    mode = "public_route"
    expectation = (
        f"public route redirects to {required_redirect_location_prefix}"
        if required_redirect_location_prefix
        else "public route resolves successfully"
    )
    try:
        status, body_text, headers, final_url = fetch(
            base_url,
            resolved_request_path,
            public_host=public_host or None,
            forwarded_proto=forwarded_proto or None,
            follow_redirects=not required_redirect_location_prefix,
            request_timeout_seconds=request_timeout_seconds,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds)
        redirect_location = headers.get("location")
        missing_texts = [snippet for snippet in required_texts if snippet not in body_text]
        final_url_ok = (
            not required_final_url_prefix
            or final_url.startswith(f"{base_url.rstrip('/')}{required_final_url_prefix}")
            or final_url.startswith(required_final_url_prefix)
        )
        success = status == 200 and not missing_texts and final_url_ok
        detail_parts = [f"expected 200 from public route, got {status}"]
        if missing_texts:
            detail_parts.append("missing required text: " + ", ".join(missing_texts))
        if not redirect_location_ok:
            detail_parts.append(
                f"redirect location {redirect_location!r} does not satisfy exact alias target {required_redirect_location_prefix!r} with an explicit empty fragment"
            )
        if not final_url_ok:
            detail_parts.append(
                f"final URL {final_url!r} does not match required prefix {required_final_url_prefix!r}"
            )
        detail = "; ".join(detail_parts)
        return RouteResult(
            path=path,
            audience=audience,
            purpose=purpose,
            requires_auth=requires_auth,
            must_exist=must_exist,
            guest_fallback=guest_fallback,
            mode=mode,
            proof_class=mode,
            positive_proof=success,
            seeded_receipt=False,
            success=success,
            status_code=status,
            final_url=final_url,
            redirect_location=redirect_location,
            expectation=expectation,
            detail=detail,
            **build_body_evidence(body_text, headers))
    except Exception as exc:
        return RouteResult(
            path=path,
            audience=audience,
            purpose=purpose,
            requires_auth=requires_auth,
            must_exist=must_exist,
            guest_fallback=guest_fallback,
            mode=mode,
            proof_class=mode,
            positive_proof=False,
            seeded_receipt=False,
            success=False,
            expectation=expectation,
            detail=f"request failed: {exc}")


def verify_negative_path(
    fetch,
    base_url: str,
    route: dict[str, Any],
    *,
    public_host: str | None,
    forwarded_proto: str | None,
    request_timeout_seconds: float,
    max_retries: int,
    retry_delay_seconds: float,
) -> NegativePathResult | None:
    verification_mode = str(route.get("verification_mode") or "").strip()
    path = str(route.get("path") or "")
    if verification_mode != "controller_contract" or not route_path_contains_placeholders(path):
        return None

    sample_path = resolve_negative_route_path_placeholders(path)
    expectation = "unknown parameterized receipt path returns bounded 404 and does not count as positive proof"
    try:
        status, _, _, final_url = fetch(
            base_url,
            sample_path,
            public_host=public_host or None,
            forwarded_proto=forwarded_proto or None,
            follow_redirects=True,
            request_timeout_seconds=request_timeout_seconds,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
        )
    except Exception as exc:
        return NegativePathResult(
            path=path,
            sample_path=sample_path,
            expectation=expectation,
            success=False,
            positive_proof=False,
            detail=f"request failed: {exc}",
        )

    success = status == 404
    return NegativePathResult(
        path=path,
        sample_path=sample_path,
        expectation=expectation,
        success=success,
        positive_proof=False,
        status_code=status,
        final_url=final_url,
        detail=f"expected bounded 404 from unknown path, got {status}",
    )


def is_transport_timeout_failure(result: RouteResult) -> bool:
    if result.success or result.status_code is not None:
        return False

    detail = (result.detail or "").casefold()
    return any(token in detail for token in TIMEOUT_FAILURE_TOKENS)


def apply_timeout_recovery_detail(recovered: RouteResult, failed: RouteResult) -> RouteResult:
    prior_detail = failed.detail or "transport timeout"
    recovered_detail = recovered.detail or "route recovered"
    return replace(
        recovered,
        detail=f"{recovered_detail}; recovered after isolated timeout retry (previous failure: {prior_detail})",
    )


def manifest_path_label(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def build_report(
    manifest: dict[str, Any],
    manifest_path: Path,
    args: argparse.Namespace,
    routes: list[RouteResult],
    negative_paths: list[NegativePathResult],
) -> dict[str, Any]:
    passed = [route for route in routes if route.success]
    failed = [route for route in routes if not route.success]
    registered = [route for route in routes if route.requires_auth]
    auth_operations = [route for route in routes if route.mode == "auth_operation"]
    public = [route for route in routes if route.mode == "public_route"]
    controller_contracts = [route for route in routes if route.mode == "controller_contract"]
    positive = [route for route in routes if route.positive_proof]
    controller_only = [route for route in controller_contracts if route.success and not route.positive_proof]
    seeded = [route for route in routes if route.seeded_receipt]
    seed_required = [route for route in routes if route.proof_class == "seed_required"]
    negative_failures = [path for path in negative_paths if not path.success]
    timeout_recovered = [route for route in routes if "recovered after isolated timeout retry" in (route.detail or "")]
    status = "pass" if not failed and not negative_failures else "fail"

    return {
        "contract_name": "chummer.public_route_proof",
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "base_url": args.base_url,
        "public_host": args.public_host or None,
        "forwarded_proto": args.forwarded_proto or None,
        "request_timeout_seconds": args.request_timeout_seconds,
        "effective_request_timeout_seconds": getattr(args, "effective_request_timeout_seconds", args.request_timeout_seconds),
        "requested_max_workers": args.max_workers,
        "effective_max_workers": getattr(args, "effective_max_workers", args.max_workers),
        "strict_positive": bool(args.strict_positive),
        "seed_receipts": bool(args.seed_receipts),
        "path_filter": list(args.path or []),
        "manifest_path": manifest_path_label(manifest_path),
        "manifest_surface": manifest.get("surface"),
        "manifest_version": manifest.get("version"),
        "summary": {
            "route_count": len(routes),
            "passed_count": len(passed),
            "failed_count": len(failed),
            "positive_proof_count": len(positive),
            "public_route_count": len(public),
            "auth_operation_count": len(auth_operations),
            "registered_route_count": len(registered),
            "controller_contract_count": len(controller_contracts),
            "controller_contract_only_count": len(controller_only),
            "negative_path_count": len(negative_paths),
            "negative_path_failed_count": len(negative_failures),
            "seeded_receipt_count": len(seeded),
            "seed_required_count": len(seed_required),
            "timeout_recovered_count": len(timeout_recovered),
            "timeout_recovered_paths": [route.path for route in timeout_recovered],
            "failed_paths": [route.path for route in failed],
        },
        "routes": [asdict(route) for route in routes],
        "negative_paths": [asdict(path) for path in negative_paths],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_workers <= 0:
        raise SystemExit("--max-workers must be positive")
    if args.timeout_recovery_seconds <= 0:
        raise SystemExit("--timeout-recovery-seconds must be positive")
    if args.timeout_recovery_retries < 0:
        raise SystemExit("--timeout-recovery-retries must be non-negative")
    manifest_path = Path(args.manifest).resolve()
    manifest, manifest_routes = read_manifest(manifest_path)
    hub_live_audit = load_hub_live_audit_module()
    active_routes = [
        route
        for route in filter_manifest_routes(manifest_routes, list(args.path or []))
        if bool(route.get("must_exist", True))
    ]

    def route_task(route: dict[str, Any]) -> RouteResult:
        return verify_route(
            hub_live_audit.fetch,
            args.base_url,
            route,
            public_host=args.public_host,
            forwarded_proto=args.forwarded_proto,
            strict_positive=bool(args.strict_positive),
            seed_receipts=bool(args.seed_receipts),
            request_timeout_seconds=effective_request_timeout_seconds,
            max_retries=args.max_retries,
            retry_delay_seconds=args.retry_delay_seconds,
        )

    def negative_task(route: dict[str, Any]) -> NegativePathResult | None:
        return verify_negative_path(
            hub_live_audit.fetch,
            args.base_url,
            route,
            public_host=args.public_host,
            forwarded_proto=args.forwarded_proto,
            request_timeout_seconds=effective_request_timeout_seconds,
            max_retries=args.max_retries,
            retry_delay_seconds=args.retry_delay_seconds,
        )

    if effective_max_workers == 1:
        results = [route_task(route) for route in active_routes]
        negative_paths = [negative for negative in (negative_task(route) for route in active_routes) if negative is not None]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=effective_max_workers) as executor:
            route_futures = [executor.submit(route_task, route) for route in active_routes]
            results = [future.result() for future in route_futures]
        with concurrent.futures.ThreadPoolExecutor(max_workers=effective_max_workers) as executor:
            negative_futures = [executor.submit(negative_task, route) for route in active_routes]
            negative_paths = [negative for negative in (future.result() for future in negative_futures) if negative is not None]

    if not args.disable_timeout_recovery:
        recovered_results: list[RouteResult] = []
        for route, result in zip(active_routes, results, strict=True):
            if not is_transport_timeout_failure(result):
                recovered_results.append(result)
                continue

            recovered = verify_route(
                hub_live_audit.fetch,
                args.base_url,
                route,
                public_host=args.public_host,
                forwarded_proto=args.forwarded_proto,
                strict_positive=bool(args.strict_positive),
                seed_receipts=bool(args.seed_receipts),
                request_timeout_seconds=args.timeout_recovery_seconds,
                max_retries=args.timeout_recovery_retries,
                retry_delay_seconds=args.retry_delay_seconds,
            )
            if recovered.success:
                recovered_results.append(apply_timeout_recovery_detail(recovered, result))
            else:
                recovered_results.append(result)
        results = recovered_results

    report = build_report(manifest, manifest_path, args, results, negative_paths)
    report_text = json.dumps(report, indent=2) + "\n"

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_text, encoding="utf-8")

    sys.stdout.write(report_text)
    return 1 if report["summary"]["failed_count"] or report["summary"]["negative_path_failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
