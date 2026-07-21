#!/usr/bin/env python3
"""Perform a read-only, generation-bound probe of all Horizon public surfaces."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import verify_horizon_live_readiness as verifier
import verify_horizon_readiness as source_verifier
import verify_live_release_convergence as convergence


CURRENT_ROUTE = "/api/v1/public/release-truth"
CAPABILITY_ROUTE = verifier.INTERNAL_CAPABILITY_ROUTE
PUBLIC_CAPABILITY_ROUTE = verifier.PUBLIC_CAPABILITY_ROUTE
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
TOKEN_RE = re.compile(r"^[!-~]{16,512}$")
SENSITIVE_KEY_RE = re.compile(r"(?:secret|credential|token|api.?key|provider.?lane)", re.I)
DECISION_STATUS_HEADER = "x-chummer-release-decision-status"
CAPABILITY_DTO_FIELDS = {
    "horizonId", "capabilityId", "artifactKind", "publicLabel",
    "capabilitySlot", "status", "internalProviderLane",
    "requiresAuthentication", "publicVisible", "freeWeeklyLimit",
    "supporterWeeklyLimit", "costClass", "quotaTracked",
    "allowanceWindowKind", "configurationEnabled", "operationalReadiness",
}


class ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes
    url: str


Transport = Callable[[str, Mapping[str, str], float, int], Response]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def now_utc_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_base_origin(value: str) -> str:
    try:
        return verifier.validate_public_https_origin(value)
    except verifier.VerificationError as error:
        raise ProbeError("base origin must be one canonical public HTTPS origin") from error


def route_url(origin: str, route: str) -> str:
    if not route.startswith("/") or route.startswith("//") or "\\" in route:
        raise ProbeError("unsafe probe route")
    parsed = urlsplit(route)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise ProbeError("unsafe probe route")
    result = origin + route
    target = urlsplit(result)
    base = urlsplit(origin)
    if (target.scheme, target.netloc) != (base.scheme, base.netloc):
        raise ProbeError("probe route escaped the configured origin")
    return result


def _default_transport(url: str, headers: Mapping[str, str], timeout: float, max_bytes: int) -> Response:
    request = Request(url, headers=dict(headers), method="GET")
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ProbeError("response exceeded configured byte limit")
            return Response(
                status=int(response.status),
                headers={str(key): str(value) for key, value in response.headers.items()},
                body=body,
                url=final_url,
            )
    except HTTPError as error:
        try:
            raise ProbeError(f"GET failed with HTTP {error.code}") from error
        finally:
            error.close()
    except URLError as error:
        raise ProbeError("GET request failed") from error


def _fetch(
    origin: str,
    route: str,
    *,
    headers: Mapping[str, str],
    timeout: float,
    max_bytes: int,
    transport: Transport,
) -> Response:
    url = route_url(origin, route)
    response = transport(url, headers, timeout, max_bytes)
    if response.status != 200:
        raise ProbeError(f"{route}: expected HTTP 200")
    if response.url != url:
        raise ProbeError(f"{route}: redirect or final-URL drift refused")
    if len(response.body) > max_bytes:
        raise ProbeError(f"{route}: response exceeded configured byte limit")
    return response


def _stable_file_bytes(path: Path, *, label: str, exact_mode: int | None = None, max_bytes: int = 16 * 1024 * 1024) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ProbeError(f"{label}: file could not be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid():
            raise ProbeError(f"{label}: file ownership/type is unsafe")
        mode = stat.S_IMODE(before.st_mode)
        if exact_mode is not None:
            if mode != exact_mode:
                raise ProbeError(f"{label}: file mode must be {exact_mode:04o}")
        elif mode & 0o022:
            raise ProbeError(f"{label}: file must not be group/world writable")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > max_bytes:
                raise ProbeError(f"{label}: file exceeds size limit")
        after = os.fstat(descriptor)
        stable = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
        )
        if not stable:
            raise ProbeError(f"{label}: file changed while being read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def read_token_file(path: Path) -> str:
    data = _stable_file_bytes(path, label="token", exact_mode=0o600, max_bytes=1024)
    try:
        token = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise ProbeError("token: must be ASCII") from error
    if token.endswith("\n"):
        token = token[:-1]
    if TOKEN_RE.fullmatch(token or "") is None or any(character.isspace() for character in token):
        raise ProbeError("token: malformed")
    return token


def _parse_input(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    data = _stable_file_bytes(path, label=label)
    try:
        return verifier.parse_json_object(data, label=label), data
    except verifier.VerificationError as error:
        raise ProbeError(str(error)) from error


def _content_type(headers: Mapping[str, str]) -> str:
    for key, value in headers.items():
        if key.casefold() == "content-type":
            return value.split(";", 1)[0].strip().lower()
    return ""


def _response_identity_binding(
    headers: Mapping[str, str],
    expected: Mapping[str, str],
    expected_truth: Mapping[str, Any],
) -> str:
    normalized = {str(key).casefold(): str(value) for key, value in headers.items()}
    projection_header = normalized.get(convergence.PROJECTION_HEADER)
    authority_header = normalized.get(
        convergence.AUTHORITY_SNAPSHOT_SHA256_HEADER
    )
    decision_header = normalized.get(DECISION_STATUS_HEADER)
    present = [projection_header is not None, authority_header is not None, decision_header is not None]
    if not any(present):
        return "not_exposed"
    if not all(present):
        raise ProbeError("response exposes a partial release identity marker set")
    try:
        projection = convergence.decode_projection_header(
            projection_header or "",
            source="Horizon response",
        )
    except Exception as error:
        raise ProbeError("response release identity marker is malformed") from error
    if projection != dict(expected_truth):
        raise ProbeError("response release identity marker drifted from committed generation")
    if authority_header != expected["authoritySnapshotSha256"]:
        raise ProbeError("response authority marker drifted from committed generation")
    if decision_header != expected_truth.get("releaseDecisionStatus"):
        raise ProbeError("response decision marker drifted from committed generation")
    return "exact"


def _current_snapshot(
    response: Response,
    expected: Mapping[str, str],
    expected_truth: Mapping[str, Any],
) -> dict[str, str]:
    if _response_identity_binding(response.headers, expected, expected_truth) != "exact":
        raise ProbeError("CURRENT did not expose exact release identity markers")
    content_type = _content_type(response.headers)
    try:
        truth = convergence.extract_route_projection(
            route=CURRENT_ROUTE,
            headers=response.headers,
            body=response.body,
            content_type=content_type,
        )
        authority_sha = convergence.extract_authority_snapshot_sha256(
            route=CURRENT_ROUTE, headers=response.headers
        )
    except Exception as error:
        raise ProbeError("CURRENT release truth is malformed or contradictory") from error
    for field in ("releaseVersion", "manifestSha256", "releaseDecisionSha256"):
        if truth.get(field) != expected[field]:
            raise ProbeError(f"CURRENT release binding mismatch: {field}")
    if authority_sha != expected["authoritySnapshotSha256"]:
        raise ProbeError("CURRENT release binding mismatch: authoritySnapshotSha256")
    if truth != dict(expected_truth):
        raise ProbeError("CURRENT full release truth does not match committed generation")
    return {
        "route": CURRENT_ROUTE,
        "releaseVersion": str(truth["releaseVersion"]),
        "manifestSha256": str(truth["manifestSha256"]),
        "releaseDecisionSha256": str(truth["releaseDecisionSha256"]),
        "releaseDecisionStatus": str(truth["releaseDecisionStatus"]),
        "authoritySnapshotSha256": authority_sha,
        "releaseTruthSha256": verifier.sha256_bytes(verifier.canonical_json_bytes(truth)),
        "responseSha256": verifier.sha256_bytes(response.body),
    }


def _reject_sensitive_catalog(value: Any, *, path: str = "catalog") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if SENSITIVE_KEY_RE.search(str(key)) and nested is not None and nested != "":
                raise ProbeError(f"{path}: publicSafe response exposed sensitive metadata")
            _reject_sensitive_catalog(nested, path=path)
    elif isinstance(value, list):
        for nested in value:
            _reject_sensitive_catalog(nested, path=path)


def _catalog_snapshot(
    response: Response,
    source: dict[str, Any],
    *,
    route: str,
    public_only: bool,
    expected: Mapping[str, str],
    expected_truth: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if _content_type(response.headers) not in {"application/json", "application/problem+json"}:
        raise ProbeError("capability catalog did not return JSON")
    try:
        payload = verifier.parse_json_object(response.body, label="capability catalog")
    except verifier.VerificationError as error:
        raise ProbeError(str(error)) from error
    if payload.get("publicSafe") is not True or set(payload) != {"publicSafe", "capabilities"}:
        raise ProbeError("capability catalog is not an exact publicSafe catalog")
    _reject_sensitive_catalog(payload)
    live_rows = payload.get("capabilities")
    if not isinstance(live_rows, list):
        raise ProbeError("capability catalog capabilities must be an array")
    source_rows = {row["capability_id"]: row for row in source.get("capabilities", []) if isinstance(row, dict) and isinstance(row.get("capability_id"), str)}
    if len(source_rows) != verifier.EXPECTED_CAPABILITY_COUNT:
        raise ProbeError("source capability denominator is not exactly 20")
    expected_ids = {
        capability_id
        for capability_id, row in source_rows.items()
        if not public_only or row.get("public_visible") is True
    }
    observed: dict[str, dict[str, Any]] = {}
    for raw in live_rows:
        if not isinstance(raw, dict):
            raise ProbeError("capability catalog row is not an object")
        if set(raw) != CAPABILITY_DTO_FIELDS:
            raise ProbeError("capability catalog DTO keyset drifted")
        capability_id = raw.get("capabilityId")
        if not isinstance(capability_id, str) or capability_id in observed:
            raise ProbeError("capability catalog has an invalid or duplicate capabilityId")
        source_row = source_rows.get(capability_id)
        if source_row is None or raw.get("horizonId") != source_row.get("horizon_id"):
            raise ProbeError("capability catalog ID/horizon set drifted")
        expected_source_fields = {
            "horizonId": source_row["horizon_id"],
            "capabilityId": source_row["capability_id"],
            "artifactKind": source_row["artifact_kind"],
            "publicLabel": source_row["public_label"],
            "capabilitySlot": source_row["capability_slot"],
            "requiresAuthentication": source_row["requires_authentication"],
            "publicVisible": source_row["public_visible"],
            "quotaTracked": source_row["quota_tracked"],
        }
        if any(raw.get(field) != value for field, value in expected_source_fields.items()):
            raise ProbeError("capability catalog DTO/source values drifted")
        for field in ("horizonId", "capabilityId", "artifactKind", "publicLabel", "capabilitySlot"):
            value = raw.get(field)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ProbeError("capability catalog DTO string field is malformed")
        for field in ("requiresAuthentication", "publicVisible", "quotaTracked", "configurationEnabled"):
            if not isinstance(raw.get(field), bool):
                raise ProbeError("capability catalog DTO boolean field is malformed")
        for field in ("freeWeeklyLimit", "supporterWeeklyLimit"):
            value = raw.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100_000:
                raise ProbeError("capability catalog DTO allowance is malformed")
        if raw.get("internalProviderLane") is not None:
            raise ProbeError("capability catalog publicSafe DTO exposed provider metadata")
        if raw.get("costClass") not in {"low", "medium", "high"}:
            raise ProbeError("capability catalog DTO costClass is malformed")
        allowance_window = raw.get("allowanceWindowKind")
        if not isinstance(allowance_window, str) or not allowance_window or allowance_window != allowance_window.strip():
            raise ProbeError("capability catalog DTO allowanceWindowKind is malformed")
        status = raw.get("status")
        enabled = raw.get("configurationEnabled")
        if status not in {"configured", "disabled"} or not isinstance(enabled, bool):
            raise ProbeError("capability configuration status is malformed")
        if (status == "configured") is not enabled:
            raise ProbeError("capability configuration fields contradict")
        operational = raw.get("operationalReadiness")
        if operational not in {"unverified", "verified"}:
            raise ProbeError("capability operational readiness is malformed")
        observed[capability_id] = raw
    if set(observed) != expected_ids:
        raise ProbeError("capability catalog denominator or public visibility set drifted")
    identity_status = _response_identity_binding(
        response.headers,
        expected,
        expected_truth,
    )
    observation = {
        "route": route,
        "httpStatus": response.status,
        "contentType": _content_type(response.headers),
        "responseSha256": verifier.sha256_bytes(response.body),
        "identityBindingStatus": identity_status,
        "rowCount": len(observed),
    }
    return observed, observation


def _capability_rows(
    internal_rows: Mapping[str, Mapping[str, Any]],
    public_rows: Mapping[str, Mapping[str, Any]],
    source: dict[str, Any],
    *,
    internal_observation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    source_rows = {
        row["capability_id"]: row
        for row in source["capabilities"]
        if isinstance(row, dict)
    }
    for capability_id, public_row in public_rows.items():
        if public_row != internal_rows.get(capability_id):
            raise ProbeError("public/internal capability DTOs contradict")
    identity_status = str(internal_observation["identityBindingStatus"])
    digest = str(internal_observation["responseSha256"])
    result: list[dict[str, Any]] = []
    for capability_id in sorted(internal_rows):
        raw = internal_rows[capability_id]
        source_row = source_rows[capability_id]
        result.append({
            "horizonId": source_row["horizon_id"],
            "capabilityId": capability_id,
            "sourceStatus": source_row["source_status"],
            "deploymentStatus": (
                "release_bound_observed"
                if identity_status == "exact"
                else "raw_http_observed"
            ),
            "configurationStatus": raw["status"],
            "operationalStatus": raw["operationalReadiness"],
            "governanceStatus": source_row["governance_status"],
            "httpStatus": 200,
            "responseSha256": digest,
            "identityBindingStatus": identity_status,
            "publicCatalogObserved": capability_id in public_rows,
        })
    return result


def _horizon_rows(
    origin: str,
    source: dict[str, Any],
    *,
    timeout: float,
    max_bytes: int,
    transport: Transport,
    expected: Mapping[str, str],
    expected_truth: Mapping[str, Any],
) -> list[dict[str, Any]]:
    source_rows = {row["horizon_id"]: row for row in source.get("horizons", []) if isinstance(row, dict) and isinstance(row.get("horizon_id"), str)}
    if set(source_rows) != set(verifier.HORIZON_ROUTES) or len(source_rows) != verifier.EXPECTED_HORIZON_COUNT:
        raise ProbeError("source horizon denominator is not exactly 15")
    result: list[dict[str, Any]] = []
    for horizon_id in sorted(source_rows):
        route = verifier.HORIZON_ROUTES[horizon_id]
        response = _fetch(
            origin, route,
            headers={"Accept": "text/html,*/*;q=0.1", "User-Agent": "chummer-horizon-readiness/1"},
            timeout=timeout, max_bytes=max_bytes, transport=transport,
        )
        content_type = _content_type(response.headers)
        if content_type not in {"text/html", "application/xhtml+xml"} or not response.body:
            raise ProbeError(f"{route}: expected a non-empty HTML response")
        identity_status = _response_identity_binding(
            response.headers,
            expected,
            expected_truth,
        )
        source_row = source_rows[horizon_id]
        result.append({
            "horizonId": horizon_id,
            "route": route,
            "sourceStatus": source_row["source_status"],
            "deploymentStatus": (
                "release_bound_reachable"
                if identity_status == "exact"
                else "raw_http_reachable"
            ),
            "configurationStatus": "not_applicable",
            "operationalStatus": source_row["runtime_status"],
            "governanceStatus": source_row["governance_status"],
            "httpStatus": response.status,
            "contentType": content_type,
            "responseSha256": verifier.sha256_bytes(response.body),
            "identityBindingStatus": identity_status,
        })
    return result


def build_receipt(
    *,
    origin: str,
    source: dict[str, Any],
    source_sha256: str,
    convergence_receipt: dict[str, Any],
    convergence_sha256: str,
    generation_manifest_file_sha256: str,
    expected: Mapping[str, str],
    token: str,
    timeout: float,
    max_response_bytes: int,
    generated_at_utc: str | None = None,
    transport: Transport = _default_transport,
) -> dict[str, Any]:
    normalized_origin = validate_base_origin(origin)
    if normalized_origin != origin:
        raise ProbeError("build_receipt requires a canonical base origin")
    common_headers = {"Accept": "application/json", "User-Agent": "chummer-horizon-readiness/1"}
    pre_response = _fetch(origin, CURRENT_ROUTE, headers=common_headers, timeout=timeout, max_bytes=max_response_bytes, transport=transport)
    expected_truth = convergence.canonicalize_projection(
        convergence_receipt.get("releaseTruth"),
        source="committed_public convergence",
    )
    pre = _current_snapshot(pre_response, expected, expected_truth)
    internal_capability_response = _fetch(
        origin, CAPABILITY_ROUTE,
        headers={**common_headers, "Authorization": f"Bearer {token}"},
        timeout=timeout, max_bytes=max_response_bytes, transport=transport,
    )
    internal_rows, internal_observation = _catalog_snapshot(
        internal_capability_response,
        source,
        route=CAPABILITY_ROUTE,
        public_only=False,
        expected=expected,
        expected_truth=expected_truth,
    )
    public_capability_response = _fetch(
        origin,
        PUBLIC_CAPABILITY_ROUTE,
        headers=common_headers,
        timeout=timeout,
        max_bytes=max_response_bytes,
        transport=transport,
    )
    public_rows, public_observation = _catalog_snapshot(
        public_capability_response,
        source,
        route=PUBLIC_CAPABILITY_ROUTE,
        public_only=True,
        expected=expected,
        expected_truth=expected_truth,
    )
    capabilities = _capability_rows(
        internal_rows,
        public_rows,
        source,
        internal_observation=internal_observation,
    )
    horizons = _horizon_rows(
        origin,
        source,
        timeout=timeout,
        max_bytes=max_response_bytes,
        transport=transport,
        expected=expected,
        expected_truth=expected_truth,
    )
    post_response = _fetch(origin, CURRENT_ROUTE, headers=common_headers, timeout=timeout, max_bytes=max_response_bytes, transport=transport)
    post = _current_snapshot(post_response, expected, expected_truth)
    if pre != post:
        raise ProbeError("CURRENT changed during the Horizon probe")

    # This v1 receipt has no digest-bound operational/governance evidence
    # authority. HTTP/configuration observations can never widen it to ready.
    operational_allowed = False
    release_binding = {
        **expected,
        "releaseDecisionStatus": convergence_receipt["releaseDecisionStatus"],
    }
    return {
        "contractName": verifier.CONTRACT_NAME,
        "contractVersion": verifier.CONTRACT_VERSION,
        "generatedAtUtc": generated_at_utc or now_utc_iso(),
        "status": "ready" if operational_allowed else "attention_required",
        "operationalReadinessClaimAllowed": operational_allowed,
        "releaseBinding": release_binding,
        "inputBindings": {
            "sourceReadinessSha256": source_sha256,
            "committedPublicConvergenceSha256": convergence_sha256,
            "generationManifestFileSha256": generation_manifest_file_sha256,
        },
        "probePolicy": {
            "baseOrigin": origin,
            "methods": ["GET"],
            "sameOriginOnly": True,
            "redirectsFollowed": False,
            "runtimeRequestsPerformed": True,
            "providerCallsPerformed": False,
            "quotaConsumed": False,
            "mutationsPerformed": False,
            "secretRedacted": True,
        },
        "currentFence": {"preCurrent": pre, "postCurrent": post, "stable": True},
        "catalogObservations": {
            "internalPublicSafe": internal_observation,
            "public": public_observation,
        },
        "summary": {
            "horizonCount": len(horizons),
            "capabilityCount": len(capabilities),
            "deploymentReachableCount": sum(
                row["deploymentStatus"]
                in {"raw_http_reachable", "release_bound_reachable"}
                for row in horizons
            ),
            "configurationConfiguredCount": sum(row["configurationStatus"] == "configured" for row in capabilities),
            "configurationDisabledCount": sum(row["configurationStatus"] == "disabled" for row in capabilities),
            "operationalReadyCount": sum(row["operationalStatus"] == "verified" for row in capabilities),
            "governanceClearedCount": sum(row["governanceStatus"] in {"cleared", "not_required"} for row in capabilities),
            "publicCapabilityCount": len(public_rows),
        },
        "horizons": horizons,
        "capabilities": capabilities,
    }


def write_new_receipt(path: Path, payload: dict[str, Any]) -> None:
    parent = path.parent.resolve()
    if path.parent.absolute() != parent or path.name in {"", ".", ".."}:
        raise ProbeError("output path must use a canonical non-symlinked parent")
    try:
        parent_stat = parent.stat()
    except OSError as error:
        raise ProbeError("output parent does not exist") from error
    if not stat.S_ISDIR(parent_stat.st_mode) or parent_stat.st_uid != os.getuid() or stat.S_IMODE(parent_stat.st_mode) & 0o022:
        raise ProbeError("output parent ownership/mode is unsafe")
    target = parent / path.name
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    data = verifier.canonical_json_bytes(payload)
    try:
        descriptor = os.open(target, flags, 0o600)
    except OSError as error:
        raise ProbeError("output must be a new file") from error
    try:
        os.fchmod(descriptor, 0o600)
        written = 0
        while written < len(data):
            written += os.write(descriptor, data[written:])
        os.fsync(descriptor)
    except OSError as error:
        os.close(descriptor)
        try:
            os.unlink(target)
        except OSError:
            pass
        raise ProbeError("output could not be written durably") from error
    else:
        os.close(descriptor)
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        directory_descriptor = os.open(parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as error:
        raise ProbeError("output directory could not be synchronized") from error


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe all Horizon surfaces using only same-origin GET requests.")
    parser.add_argument(
        "--base-url",
        default=verifier.PRODUCTION_ORIGIN,
        choices=[verifier.PRODUCTION_ORIGIN],
        help="Pinned production origin; alternate hosts and ports are refused.",
    )
    parser.add_argument("--source-readiness", type=Path, required=True)
    parser.add_argument("--expected-source-readiness-sha256", required=True)
    parser.add_argument("--committed-public-convergence", type=Path, required=True)
    parser.add_argument("--expected-committed-public-convergence-sha256", required=True)
    parser.add_argument("--generation-manifest", type=Path, required=True)
    parser.add_argument("--expected-generation-manifest-file-sha256", required=True)
    parser.add_argument("--expected-release-version", required=True)
    parser.add_argument("--expected-generation-id", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-release-decision-sha256", required=True)
    parser.add_argument("--expected-authority-snapshot-sha256", required=True)
    parser.add_argument("--internal-token-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-response-bytes", type=int, default=DEFAULT_MAX_RESPONSE_BYTES)
    parser.add_argument("--max-age-seconds", type=int, default=verifier.DEFAULT_MAX_AGE_SECONDS)
    parser.add_argument("--allowed-future-skew-seconds", type=int, default=verifier.DEFAULT_ALLOWED_FUTURE_SKEW_SECONDS)
    parser.add_argument(
        "--allow-attention-required",
        action="store_true",
        help=(
            "Observation-only mode: exit zero after writing a valid "
            "attention_required receipt. Without this flag it remains a "
            "non-zero release gate."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.timeout <= 0 or args.timeout > 60 or args.max_response_bytes <= 0 or args.max_response_bytes > 8 * 1024 * 1024:
            raise ProbeError("timeout/response-size policy is invalid")
        origin = validate_base_origin(args.base_url)
        expected = verifier.expected_binding(
            args.expected_release_version, args.expected_generation_id,
            args.expected_manifest_sha256, args.expected_release_decision_sha256,
            args.expected_authority_snapshot_sha256,
        )
        source, source_bytes = _parse_input(args.source_readiness, label="source")
        convergence_receipt, convergence_bytes = _parse_input(args.committed_public_convergence, label="convergence")
        generation_manifest_bytes = _stable_file_bytes(
            args.generation_manifest,
            label="generation_manifest",
        )
        source_sha = verifier.sha256_bytes(source_bytes)
        convergence_sha = verifier.sha256_bytes(convergence_bytes)
        generation_manifest_sha = verifier.sha256_bytes(generation_manifest_bytes)
        if source_sha != args.expected_source_readiness_sha256:
            raise ProbeError("source readiness digest mismatch")
        if convergence_sha != args.expected_committed_public_convergence_sha256:
            raise ProbeError("committed_public convergence digest mismatch")
        if generation_manifest_sha != args.expected_generation_manifest_file_sha256:
            raise ProbeError("generation manifest file digest mismatch")
        now = datetime.now(UTC)
        source_ok, source_issues = source_verifier.verify_payload(
            source, args.repo_root.resolve(),
            args.repo_root / ".codex-design/product/HORIZON_REGISTRY.yaml",
            args.repo_root / "Chummer.Run.Api/Services/Community/HorizonCapabilityService.cs",
            max_age_seconds=args.max_age_seconds,
            allowed_future_skew_seconds=args.allowed_future_skew_seconds,
            now_utc=now,
        )
        if not source_ok or not source_verifier.source_working_claim_allowed(source):
            raise ProbeError("source readiness input is not current and source-working")
        convergence_issues, _ = verifier.validate_convergence(
            convergence_receipt,
            expected,
            generation_manifest_bytes=generation_manifest_bytes,
        )
        convergence_issues.extend(verifier._timestamp_issues(
            convergence_receipt.get("generatedAtUtc"), now,
            args.max_age_seconds, args.allowed_future_skew_seconds,
            "convergence:generatedAtUtc",
        ))
        if convergence_issues:
            raise ProbeError("committed_public convergence input is invalid")
        token = read_token_file(args.internal_token_file)
        receipt = build_receipt(
            origin=origin, source=source, source_sha256=source_sha,
            convergence_receipt=convergence_receipt, convergence_sha256=convergence_sha,
            generation_manifest_file_sha256=generation_manifest_sha,
            expected=expected, token=token, timeout=args.timeout,
            max_response_bytes=args.max_response_bytes,
        )
        ok, receipt_issues = verifier.verify_receipt(
            receipt, source, convergence_receipt,
            source_sha256=source_sha, convergence_sha256=convergence_sha,
            generation_manifest_sha256=generation_manifest_sha,
            generation_manifest_bytes=generation_manifest_bytes,
            expected=expected, repo_root=args.repo_root,
            max_age_seconds=args.max_age_seconds,
            allowed_future_skew_seconds=args.allowed_future_skew_seconds,
            now_utc=now,
        )
        if not ok:
            raise ProbeError("constructed receipt failed offline verification: " + ",".join(receipt_issues[:3]))
        write_new_receipt(args.output, receipt)
    except (ProbeError, verifier.VerificationError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1
    if receipt["status"] == "attention_required" and not args.allow_attention_required:
        print(
            json.dumps(
                {
                    "status": "attention_required",
                    "output": args.output.resolve().as_posix(),
                    "release_gate_passed": False,
                },
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "pass",
                "output": args.output.resolve().as_posix(),
                "release_gate_passed": receipt["status"] == "ready",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
