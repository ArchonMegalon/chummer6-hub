#!/usr/bin/env python3
"""Verify the serving-only public runtime and its fail-closed private boundary."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, NamedTuple
from urllib.parse import ParseResult, unquote, urljoin, urlparse

import requests


CONTRACT_NAME = "chummer.public-download-only-postdeploy/v1"
READINESS_CONTRACT = "chummer.run.api.public_downloads_readiness.v1"
GENERATION_HEADER = "X-Chummer-Release-Generation"
SIDECAR_CONTRACT = "chummer6-ui.windows_bootstrap_payload"
STREAM_CHUNK_BYTES = 64 * 1024
MAXIMUM_MANIFEST_BYTES = 8 * 1024 * 1024
PROBLEM = {
    "type": "https://chummer.run/problems/install-linking-unavailable",
    "title": "Install-linking unavailable.",
    "status": 503,
    "detail": "Install-linking is temporarily unavailable.",
}
UNAVAILABLE_READINESS_PATHS = (
    "/api/ready",
    "/api/ready/publication",
    "/api/ready/install-linking-authority",
)
PRIVATE_PATHS = (
    "/api/v1/install-linking/me",
    "/account/access/install-link",
)
INSTALL_ROUTE_DENIAL_PATHS = (
    "/downloads/install/public-download-only-probe",
)
FORBIDDEN_RESPONSE_HEADERS = (
    "Authorization",
    "Authentication-Info",
    "Location",
    "Proxy-Authenticate",
    "Proxy-Authentication-Info",
    "Proxy-Authorization",
    "Refresh",
    "Set-Cookie",
    "Set-Cookie2",
    "WWW-Authenticate",
)
CREDENTIAL_REQUEST_HEADERS = (
    "Authorization",
    "Cookie",
    "Proxy-Authorization",
)
DELIVERY_PHASE_BOOTSTRAP = "bootstrap"
DELIVERY_PHASE_WINDOWS_PREVIEW = "windows-preview"
DELIVERY_PHASES = (
    DELIVERY_PHASE_BOOTSTRAP,
    DELIVERY_PHASE_WINDOWS_PREVIEW,
)
REVIEW_REQUIRED_RELEASE_TRUTH_KEYS = frozenset(
    {
        "artifactCount",
        "artifactHandoff",
        "availablePlatforms",
        "channel",
        "contractName",
        "downloadAccessPosture",
        "knownIssueSummary",
        "manifestSha256",
        "primaryHeadByPlatform",
        "registryCommit",
        "releaseDecisionSha256",
        "releaseDecisionStatus",
        "releaseScopeDecisionSha256",
        "releaseStatus",
        "releaseVersion",
        "rolloutState",
        "supportabilityState",
    }
)
REVIEW_REQUIRED_ARTIFACT_HANDOFF_KEYS = frozenset(
    {
        "arch",
        "artifactAccessClass",
        "artifactId",
        "channel",
        "contractName",
        "downloadUrl",
        "head",
        "platform",
        "publicInstallRoute",
        "releaseScopeDecisionSha256",
        "releaseVersion",
        "rid",
        "sha256",
        "signingRequirement",
        "sizeBytes",
        "sourcePublicationState",
        "status",
    }
)


class DownloadExpectation(NamedTuple):
    artifact_id: str
    release_version: str
    head: str
    rid: str
    arch: str
    installer_file_name: str
    installer_url: str
    installer_sha256: str
    installer_size_bytes: int
    payload_file_name: str
    manifest_payload_url: str
    payload_url: str
    payload_probe_url: str
    payload_sha256: str
    payload_size_bytes: int
    sidecar_file_name: str
    sidecar_url: str
    sidecar_probe_url: str
    sidecar_sha256: str
    sidecar_size_bytes: int
    sidecar_bytes: bytes


class AnonymousAuth(requests.auth.AuthBase):
    """Prevent requests/netrc from attaching ambient credentials."""

    def __call__(self, request: requests.PreparedRequest) -> requests.PreparedRequest:
        for header in CREDENTIAL_REQUEST_HEADERS:
            request.headers.pop(header, None)
        return request


def anonymous_session() -> requests.Session:
    """Create one transport that cannot inherit ambient proxy or account state."""

    session = requests.Session()
    session.trust_env = False
    session.auth = AnonymousAuth()
    session.cookies.clear()
    return session


class AnonymousRequestsAdapter:
    """Route the legacy truth gate through the same anonymous transport."""

    RequestException = requests.RequestException

    def __init__(self, session: requests.Session) -> None:
        self._session = session

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        kwargs["allow_redirects"] = False
        kwargs["auth"] = AnonymousAuth()
        kwargs["cookies"] = {}
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Accept-Encoding", "identity")
        kwargs["headers"] = headers
        self._session.cookies.clear()
        return self._session.get(url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> requests.Response:
        kwargs["allow_redirects"] = False
        kwargs["auth"] = AnonymousAuth()
        kwargs["cookies"] = {}
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Accept-Encoding", "identity")
        kwargs["headers"] = headers
        self._session.cookies.clear()
        return self._session.head(url, **kwargs)


def load_truth_gate(source_root: Path) -> Any:
    path = source_root / "scripts" / "public_download_shelf_truth_gate.py"
    if not path.is_file() or path.is_symlink():
        raise ValueError("public download truth gate is unavailable")
    spec = importlib.util.spec_from_file_location(
        "chummer_public_download_only_truth_gate",
        path,
    )
    if spec is None or spec.loader is None:
        raise ValueError("public download truth gate could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def anonymous_get(
    session: requests.Session,
    url: str,
    timeout: float,
    *,
    stream: bool,
) -> requests.Response:
    session.cookies.clear()
    return session.get(
        url,
        timeout=timeout,
        headers={
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        auth=AnonymousAuth(),
        cookies={},
        allow_redirects=False,
        stream=stream,
    )


def get(
    session: requests.Session,
    base_url: str,
    path: str,
    timeout: float,
) -> requests.Response:
    session.cookies.clear()
    return session.get(
        base_url.rstrip("/") + path,
        timeout=timeout,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        auth=AnonymousAuth(),
        cookies={},
        allow_redirects=False,
    )


def require_json(response: requests.Response, label: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except (requests.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} response is not JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} response is not an object")
    return payload


def _header(headers: Mapping[str, Any], name: str) -> tuple[bool, str]:
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered:
            return True, str(value)
    return False, ""


def _media_type(headers: Mapping[str, Any]) -> str:
    present, value = _header(headers, "Content-Type")
    if not present:
        return ""
    return value.split(";", 1)[0].strip().lower()


def _reject_credential_headers(response: requests.Response, label: str) -> None:
    for name in FORBIDDEN_RESPONSE_HEADERS:
        present, _ = _header(response.headers, name)
        if present:
            raise ValueError(f"{label} exposed forbidden response header {name}")

    present, content_encoding = _header(response.headers, "Content-Encoding")
    if present and content_encoding.strip().lower() != "identity":
        raise ValueError(
            f"{label} used unexpected Content-Encoding {content_encoding!r}"
        )

    request = getattr(response, "request", None)
    request_headers = getattr(request, "headers", {}) if request is not None else {}
    for name in CREDENTIAL_REQUEST_HEADERS:
        present, _ = _header(request_headers, name)
        if present:
            raise ValueError(f"{label} request carried credential header {name}")


def _origin(parsed: ParseResult) -> tuple[str, str, int | None]:
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("download URL has an invalid port") from exc
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port


def _validated_base_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    parsed = urlparse(base)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base URL must be credential-free HTTPS origin and path")
    _origin(parsed)
    return base


def _download_url(base_url: str, value: Any, label: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{label} URL is missing")
    resolved = urljoin(base_url.rstrip("/") + "/", raw)
    parsed = urlparse(resolved)
    base = urlparse(base_url)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
        or _origin(parsed) != _origin(base)
        or not parsed.path.startswith("/downloads/")
    ):
        raise ValueError(f"{label} URL is not a credential-free same-origin download URL")
    return resolved


def _canonical_payload_url(base_url: str, value: Any, label: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{label} URL is missing")
    raw_parsed = urlparse(raw)
    if not raw_parsed.scheme or not raw_parsed.netloc:
        raise ValueError(f"{label} URL must be an absolute HTTPS URL")
    resolved = raw
    parsed = urlparse(resolved)
    base = urlparse(base_url)
    same_origin = _origin(parsed) == _origin(base)
    canonical_apex_for_www = (
        base.hostname == "www.chummer.run"
        and parsed.hostname == "chummer.run"
        and parsed.scheme.lower() == base.scheme.lower()
        and parsed.port == base.port
    )
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
        or not (same_origin or canonical_apex_for_www)
        or not parsed.path.startswith("/downloads/")
    ):
        raise ValueError(
            f"{label} URL is not a credential-free public download URL"
        )
    return resolved


def _decoded_payload_path(url: str) -> str:
    path = urlparse(url).path
    offset = 0
    while offset < len(path):
        if path[offset] != "%":
            offset += 1
            continue
        escape = path[offset : offset + 3]
        if len(escape) != 3 or escape[1:].lower() != "2b":
            raise ValueError(
                "payload URL contains noncanonical percent encoding"
            )
        offset += 3
    # Deliberately not unquote_plus: '+' is a literal path character.
    return unquote(path)


def _host_local_mirror_url(base_url: str, canonical_url: str) -> str:
    base = urlparse(base_url)
    canonical = urlparse(canonical_url)
    return canonical._replace(
        scheme=base.scheme,
        netloc=base.netloc,
        path=_decoded_payload_path(canonical_url),
    ).geturl()


def _sidecar_url(payload_url: str) -> str:
    parsed = urlparse(payload_url)
    return parsed._replace(path=parsed.path + ".json").geturl()


def _required_text(payload: Mapping[str, Any], key: str, label: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{label} is missing {key}")
    return value


def _required_size(payload: Mapping[str, Any], key: str, label: str) -> int:
    try:
        value = int(payload.get(key))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} has invalid {key}") from exc
    if value <= 0:
        raise ValueError(f"{label} has invalid {key}")
    return value


def _required_sha256(payload: Mapping[str, Any], key: str, label: str) -> str:
    value = _required_text(payload, key, label).lower()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} has invalid {key}")
    return value


def _required_git_commit(
    payload: Mapping[str, Any],
    key: str,
    label: str,
) -> str:
    value = _required_text(payload, key, label).lower()
    if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} has invalid {key}")
    return value


def _safe_generation_segment(generation_id: str | None) -> str | None:
    if not generation_id:
        return None
    if (
        Path(generation_id).name != generation_id
        or generation_id in {".", ".."}
        or "/" in generation_id
        or "\\" in generation_id
    ):
        raise ValueError("local manifest generation id is not a safe path segment")
    return generation_id


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} is not a JSON object")
    return payload


def _canonical_object_sha256(payload: Mapping[str, Any]) -> str:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _regular_file_bytes(path: Path, label: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is not a regular local file: {path}")
    return path.read_bytes()


def _find_sidecar_bytes(
    local_manifest_path: Path,
    local_canonical_manifest_path: Path,
    sidecar_file_name: str,
    generation_id: str | None,
) -> bytes:
    generation_id = _safe_generation_segment(generation_id)
    roots = [
        local_manifest_path.parent / "files",
        local_canonical_manifest_path.parent / "files",
        local_manifest_path.parent / "bundle" / "files",
        local_canonical_manifest_path.parent / "bundle" / "files",
    ]
    if generation_id:
        for parent in {
            local_manifest_path.parent,
            local_canonical_manifest_path.parent,
        }:
            roots.append(
                parent / "generations" / generation_id / "files"
            )
            if (
                parent.name == generation_id
                and parent.parent.name == "generations"
            ):
                roots.append(parent / "files")
    matches: list[bytes] = []
    for root in dict.fromkeys(roots):
        path = root / sidecar_file_name
        if path.is_file() and not path.is_symlink():
            matches.append(path.read_bytes())
    if not matches:
        raise ValueError(f"local bootstrap sidecar is missing: {sidecar_file_name}")
    if any(candidate != matches[0] for candidate in matches[1:]):
        raise ValueError(f"local bootstrap sidecar copies disagree: {sidecar_file_name}")
    return matches[0]


def _rows(payload: Mapping[str, Any], key: str, label: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{label} is missing {key}")
    return [row for row in value if isinstance(row, dict)]


def _row_platform_is_windows(row: Mapping[str, Any]) -> bool:
    platform = str(row.get("platform") or "").strip().lower()
    rid = str(row.get("rid") or "").strip().lower()
    return platform in {"win", "windows"} or rid.startswith("win-")


def _windows_bootstrap_rows(
    payload: Mapping[str, Any],
    *,
    key: str,
    label: str,
) -> list[dict[str, Any]]:
    return [
        row
        for row in _rows(payload, key, label)
        if _row_platform_is_windows(row)
        and str(row.get("kind") or "").strip().lower() == "installer"
        and str(row.get("installerMode") or "").strip().lower() == "bootstrap"
    ]


def _require_delivery_phase_shape(
    *,
    delivery_phase: str,
    canonical: Mapping[str, Any],
    compatibility: Mapping[str, Any],
) -> list[dict[str, Any]]:
    canonical_rows = _windows_bootstrap_rows(
        canonical,
        key="artifacts",
        label="local canonical manifest",
    )
    compatibility_rows = _windows_bootstrap_rows(
        compatibility,
        key="downloads",
        label="local compatibility manifest",
    )
    if delivery_phase == DELIVERY_PHASE_BOOTSTRAP:
        if canonical_rows or compatibility_rows:
            raise ValueError(
                "bootstrap delivery phase requires zero Windows bootstrap rows"
            )
        return []
    if delivery_phase != DELIVERY_PHASE_WINDOWS_PREVIEW:
        raise ValueError("delivery phase is invalid")
    if not canonical_rows:
        raise ValueError("canonical manifest has no Windows bootstrap installer")
    canonical_ids = {
        str(row.get("artifactId") or row.get("id") or "").strip()
        for row in canonical_rows
    }
    compatibility_ids = {
        str(row.get("artifactId") or row.get("id") or "").strip()
        for row in compatibility_rows
    }
    if (
        "" in canonical_ids
        or "" in compatibility_ids
        or canonical_ids != compatibility_ids
    ):
        raise ValueError(
            "canonical and compatibility Windows bootstrap row sets disagree"
        )
    return canonical_rows


def _assert_manifest_policy(
    canonical: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> None:
    artifact_id = _required_text(artifact, "artifactId", "Windows artifact")
    version = _required_text(canonical, "version", "canonical manifest")
    channel = str(canonical.get("channelId") or canonical.get("channel") or "").strip().lower()
    if channel != "preview":
        raise ValueError("canonical manifest channel is not preview")
    if str(canonical.get("supportabilityState") or "").strip().lower() != "review_required":
        raise ValueError("canonical manifest supportability is not review-required")
    if str(canonical.get("status") or "").strip().lower() != "published":
        raise ValueError("canonical manifest is not published")
    if str(canonical.get("rolloutState") or "").strip().lower() == "public_stable":
        raise ValueError("canonical manifest unexpectedly claims stable rollout")
    if any(canonical.get(key) is True for key in ("stable", "isStable", "update", "updateEligible")):
        raise ValueError("canonical manifest unexpectedly claims stable/update eligibility")

    if str(artifact.get("channelId") or artifact.get("channel") or "").strip().lower() != "preview":
        raise ValueError(f"{artifact_id} is not a preview artifact")
    if str(artifact.get("installAccessClass") or "").strip().lower() != "open_public":
        raise ValueError(f"{artifact_id} is not open_public")
    if (
        "artifactByteVisibility" in artifact
        and str(artifact.get("artifactByteVisibility") or "").strip().lower()
        != "public"
    ):
        raise ValueError(f"{artifact_id} byte visibility is not public")
    if str(artifact.get("installerMode") or "").strip().lower() != "bootstrap":
        raise ValueError(f"{artifact_id} is not a bootstrap installer")
    if str(artifact.get("payloadAcquisitionMode") or "").strip().lower() != "download":
        raise ValueError(f"{artifact_id} payload acquisition is not download")
    if (
        "previewPolicy" in artifact
        and str(artifact.get("previewPolicy") or "").strip().lower()
        != "preview_policy"
    ):
        raise ValueError(f"{artifact_id} preview policy is invalid")
    if artifact.get("publicInstallRoute") is not None:
        raise ValueError(f"{artifact_id} unexpectedly claims a public install route")
    if any(artifact.get(key) is True for key in ("stable", "stableEligible", "update", "updateEligible")):
        raise ValueError(f"{artifact_id} unexpectedly claims stable/update eligibility")
    if str(artifact.get("version") or artifact.get("releaseVersion") or "").strip() != version:
        raise ValueError(f"{artifact_id} release version disagrees with the manifest")

    if "signature" in artifact:
        signature = artifact.get("signature")
        if not isinstance(signature, dict) or (
            str(signature.get("status") or "").strip().lower() != "unsigned"
            or str(signature.get("policy") or "").strip().lower()
            != "preview_policy"
            or signature.get("required") is not False
        ):
            raise ValueError(
                f"{artifact_id} is not unsigned under preview_policy"
            )

    coverage = canonical.get("desktopTupleCoverage")
    route_rows = coverage.get("desktopRouteTruth") if isinstance(coverage, dict) else None
    matching_routes = [
        row
        for row in route_rows or []
        if isinstance(row, dict)
        and str(row.get("artifactId") or "").strip() == artifact_id
    ]
    if len(matching_routes) != 1:
        raise ValueError(f"{artifact_id} does not have exactly one route-truth row")
    route = matching_routes[0]
    normalized_route_schema = any(
        key in route
        for key in ("routeAuthority", "publicationState", "visibility")
    )
    promotion = str(route.get("promotionState") or "").strip().lower()
    update = str(route.get("updateEligibility") or "").strip().lower()
    if normalized_route_schema:
        if (
            route.get("publicInstallRoute") is not None
            or route.get("routeAuthority") is not False
            or str(route.get("publicationState") or "").strip().lower()
            != "preview"
            or str(route.get("visibility") or "").strip().lower()
            != "public_artifact_only"
            or promotion in {"promoted", "public_stable", "stable"}
            or not promotion
        ):
            raise ValueError(
                f"{artifact_id} route truth unexpectedly claims stable/install authority"
            )
        if (
            update
            in {
                "eligible",
                "automatic",
                "auto",
                "auto_update",
                "enabled",
                "true",
            }
            or not update
        ):
            raise ValueError(
                f"{artifact_id} route truth unexpectedly claims update eligibility"
            )
    else:
        # Layout-v1 authority bytes predate the normalized route fields and are
        # intentionally immutable. The authenticated releaseTruth wrapper and
        # runtime 409 boundary conservatively supersede this exact legacy shape.
        legacy_install_route = str(
            route.get("publicInstallRoute") or ""
        ).strip()
        if (
            promotion != "promoted"
            or update != "eligible"
            or legacy_install_route
            != f"/downloads/install/{artifact_id}"
        ):
            raise ValueError(
                f"{artifact_id} legacy route truth shape is not recognized"
            )


def _validate_sidecar(payload: Mapping[str, Any], expected: DownloadExpectation) -> None:
    if str(payload.get("contractName") or "").strip() != SIDECAR_CONTRACT:
        raise ValueError("bootstrap sidecar has unexpected contractName")
    if str(payload.get("releaseVersion") or "").strip() != expected.release_version:
        raise ValueError("bootstrap sidecar releaseVersion disagrees with manifest")
    if str(payload.get("fileName") or "").strip() != expected.payload_file_name:
        raise ValueError("bootstrap sidecar fileName disagrees with manifest")
    if str(payload.get("installerFileName") or "").strip() != expected.installer_file_name:
        raise ValueError("bootstrap sidecar installerFileName disagrees with manifest")
    if str(payload.get("payloadAcquisitionMode") or "").strip().lower() != "download":
        raise ValueError("bootstrap sidecar payload acquisition is not download")
    raw_download_url = str(payload.get("downloadUrl") or "").strip()
    normalized_download_url = _canonical_payload_url(
        expected.installer_url,
        raw_download_url,
        "bootstrap sidecar payload",
    )
    if _host_local_mirror_url(
        expected.installer_url,
        normalized_download_url,
    ) != _host_local_mirror_url(expected.installer_url, expected.payload_url):
        raise ValueError("bootstrap sidecar downloadUrl disagrees with manifest")
    if str(payload.get("sha256") or "").strip().lower() != expected.payload_sha256:
        raise ValueError("bootstrap sidecar sha256 disagrees with manifest")
    try:
        size = int(payload.get("sizeBytes"))
    except (TypeError, ValueError) as exc:
        raise ValueError("bootstrap sidecar sizeBytes is invalid") from exc
    if size != expected.payload_size_bytes:
        raise ValueError("bootstrap sidecar sizeBytes disagrees with manifest")


def derive_download_expectations(
    *,
    base_url: str,
    local_manifest_path: Path,
    local_canonical_manifest_path: Path,
) -> tuple[bytes, str | None, list[DownloadExpectation]]:
    base = _validated_base_url(base_url)
    canonical_bytes = _regular_file_bytes(
        local_canonical_manifest_path,
        "local canonical manifest",
    )
    manifest_bytes = _regular_file_bytes(local_manifest_path, "local compatibility manifest")
    canonical = _json_object(canonical_bytes, "local canonical manifest")
    compatibility = _json_object(manifest_bytes, "local compatibility manifest")

    canonical_generation = str(canonical.get("generationId") or "").strip()
    compatibility_generation = str(compatibility.get("generationId") or "").strip()
    if (
        canonical_generation
        and compatibility_generation
        and canonical_generation != compatibility_generation
    ):
        raise ValueError("local manifest generation ids disagree")
    expected_generation = canonical_generation or compatibility_generation or None

    canonical_rows = _require_delivery_phase_shape(
        delivery_phase=DELIVERY_PHASE_WINDOWS_PREVIEW,
        canonical=canonical,
        compatibility=compatibility,
    )

    compatibility_by_id = {
        str(row.get("artifactId") or row.get("id") or "").strip(): row
        for row in _rows(compatibility, "downloads", "local compatibility manifest")
    }
    expectations: list[DownloadExpectation] = []
    version = _required_text(canonical, "version", "canonical manifest")
    for artifact in canonical_rows:
        _assert_manifest_policy(canonical, artifact)
        artifact_id = _required_text(artifact, "artifactId", "Windows artifact")
        head = _required_text(artifact, "head", artifact_id)
        rid = _required_text(artifact, "rid", artifact_id)
        arch = _required_text(artifact, "arch", artifact_id)
        compatibility_row = compatibility_by_id.get(artifact_id)
        if compatibility_row is None:
            raise ValueError(f"compatibility manifest is missing {artifact_id}")

        installer_file_name = _required_text(artifact, "fileName", artifact_id)
        payload_file_name = _required_text(artifact, "payloadFileName", artifact_id)
        installer_url = _download_url(
            base,
            artifact.get("downloadUrl") or artifact.get("url"),
            f"{artifact_id} installer",
        )
        manifest_payload_url = _download_url(
            base,
            artifact.get("payloadDownloadUrl"),
            f"{artifact_id} manifest payload",
        )
        if Path(urlparse(installer_url).path).name != installer_file_name:
            raise ValueError(f"{artifact_id} installer URL filename disagrees with manifest")
        # URL paths preserve literal '+'. Decode percent escapes without applying
        # form/query semantics, where '+' would incorrectly become a space.
        payload_path = _decoded_payload_path(manifest_payload_url)
        if not expected_generation:
            raise ValueError(
                f"{artifact_id} payload URL cannot be generation-bound without a generation id"
            )
        expected_payload_path = (
            f"/downloads/g/{expected_generation}/files/{payload_file_name}"
        )
        if payload_path != expected_payload_path:
            raise ValueError(
                f"{artifact_id} open_public payload URL must be the generation-bound files route"
            )

        installer_sha256 = _required_sha256(artifact, "sha256", artifact_id)
        installer_size = _required_size(artifact, "sizeBytes", artifact_id)
        payload_sha256 = _required_sha256(artifact, "payloadSha256", artifact_id)
        payload_size = _required_size(artifact, "payloadSizeBytes", artifact_id)

        compatibility_values = {
            "installer_file_name": str(compatibility_row.get("fileName") or "").strip(),
            "installer_url": _download_url(
                base,
                compatibility_row.get("downloadUrl") or compatibility_row.get("url"),
                f"{artifact_id} compatibility installer",
            ),
            "installer_sha256": str(compatibility_row.get("sha256") or "").strip().lower(),
            "installer_size": int(compatibility_row.get("sizeBytes") or 0),
            "payload_file_name": str(compatibility_row.get("payloadFileName") or "").strip(),
            "manifest_payload_url": _download_url(
                base,
                compatibility_row.get("payloadDownloadUrl"),
                f"{artifact_id} compatibility payload",
            ),
            "payload_sha256": str(compatibility_row.get("payloadSha256") or "").strip().lower(),
            "payload_size": int(compatibility_row.get("payloadSizeBytes") or 0),
            "access": str(compatibility_row.get("installAccessClass") or "").strip().lower(),
            "mode": str(compatibility_row.get("installerMode") or "").strip().lower(),
        }
        expected_values = {
            "installer_file_name": installer_file_name,
            "installer_url": installer_url,
            "installer_sha256": installer_sha256,
            "installer_size": installer_size,
            "payload_file_name": payload_file_name,
            "manifest_payload_url": manifest_payload_url,
            "payload_sha256": payload_sha256,
            "payload_size": payload_size,
            "access": "open_public",
            "mode": "bootstrap",
        }
        if compatibility_values != expected_values:
            raise ValueError(f"canonical and compatibility metadata disagree for {artifact_id}")

        sidecar_file_name = payload_file_name + ".json"
        sidecar_bytes = _find_sidecar_bytes(
            local_manifest_path,
            local_canonical_manifest_path,
            sidecar_file_name,
            expected_generation,
        )
        sidecar_payload = _json_object(
            sidecar_bytes,
            f"local {sidecar_file_name}",
        )
        sidecar_payload_url = _canonical_payload_url(
            base,
            sidecar_payload.get("downloadUrl"),
            f"{artifact_id} sidecar payload",
        )
        if _host_local_mirror_url(
            base,
            sidecar_payload_url,
        ) != _host_local_mirror_url(base, manifest_payload_url):
            raise ValueError(
                f"{artifact_id} sidecar payload URL disagrees with manifest"
            )
        payload_url = manifest_payload_url
        expectation = DownloadExpectation(
            artifact_id=artifact_id,
            release_version=version,
            head=head,
            rid=rid,
            arch=arch,
            installer_file_name=installer_file_name,
            installer_url=installer_url,
            installer_sha256=installer_sha256,
            installer_size_bytes=installer_size,
            payload_file_name=payload_file_name,
            manifest_payload_url=manifest_payload_url,
            payload_url=payload_url,
            payload_probe_url=_host_local_mirror_url(base, payload_url),
            payload_sha256=payload_sha256,
            payload_size_bytes=payload_size,
            sidecar_file_name=sidecar_file_name,
            sidecar_url=_sidecar_url(payload_url),
            sidecar_probe_url=_host_local_mirror_url(
                base,
                _sidecar_url(payload_url),
            ),
            sidecar_sha256=hashlib.sha256(sidecar_bytes).hexdigest(),
            sidecar_size_bytes=len(sidecar_bytes),
            sidecar_bytes=sidecar_bytes,
        )
        _validate_sidecar(
            sidecar_payload,
            expectation,
        )
        expectations.append(expectation)
    return canonical_bytes, expected_generation, expectations


def _stream_exact_get(
    *,
    session: requests.Session,
    url: str,
    label: str,
    expected_sha256: str,
    expected_size_bytes: int,
    timeout: float,
    generation_id: str | None,
    capture: bool,
) -> tuple[dict[str, Any], bytes]:
    response = anonymous_get(session, url, timeout, stream=True)
    try:
        if response.status_code != 200:
            raise ValueError(f"{label} expected HTTP 200, got {response.status_code}")
        if getattr(response, "history", []):
            raise ValueError(f"{label} followed an unexpected redirect")
        response_url = str(getattr(response, "url", url) or url)
        if response_url != url:
            raise ValueError(f"{label} resolved to an unexpected URL")
        _reject_credential_headers(response, label)

        present, raw_length = _header(response.headers, "Content-Length")
        if not present:
            raise ValueError(f"{label} is missing Content-Length")
        try:
            content_length = int(raw_length)
        except ValueError as exc:
            raise ValueError(f"{label} has invalid Content-Length") from exc
        if content_length != expected_size_bytes:
            raise ValueError(
                f"{label} Content-Length {content_length} does not match expected "
                f"{expected_size_bytes}"
            )

        present, observed_generation = _header(response.headers, GENERATION_HEADER)
        observed_generation = observed_generation.strip()
        if not present or not observed_generation:
            raise ValueError(f"{label} is missing {GENERATION_HEADER}")
        if generation_id is not None and observed_generation != generation_id:
            raise ValueError(
                f"{label} generation {observed_generation!r} does not match "
                f"{generation_id!r}"
            )

        digest = hashlib.sha256()
        size = 0
        body_parts: list[bytes] = []
        for chunk in response.iter_content(chunk_size=STREAM_CHUNK_BYTES):
            if not chunk:
                continue
            digest.update(chunk)
            size += len(chunk)
            if size > expected_size_bytes:
                raise ValueError(f"{label} streamed more bytes than expected")
            if capture:
                body_parts.append(chunk)
        observed_sha256 = digest.hexdigest()
        if size != content_length or size != expected_size_bytes:
            raise ValueError(f"{label} streamed size {size} does not match Content-Length")
        if observed_sha256 != expected_sha256:
            raise ValueError(f"{label} streamed sha256 does not match expected bytes")
        return (
            {
                "method": "GET",
                "url": url,
                "statusCode": 200,
                "contentLength": content_length,
                "sizeBytes": size,
                "sha256": observed_sha256,
                "generationId": observed_generation,
            },
            b"".join(body_parts),
        )
    finally:
        response.close()


def _stream_manifest_get(
    *,
    session: requests.Session,
    url: str,
    label: str,
    timeout: float,
    generation_id: str | None,
) -> tuple[dict[str, Any], bytes]:
    response = anonymous_get(session, url, timeout, stream=True)
    try:
        if response.status_code != 200:
            raise ValueError(f"{label} expected HTTP 200, got {response.status_code}")
        if getattr(response, "history", []):
            raise ValueError(f"{label} followed an unexpected redirect")
        response_url = str(getattr(response, "url", url) or url)
        if response_url != url:
            raise ValueError(f"{label} resolved to an unexpected URL")
        _reject_credential_headers(response, label)

        generation_present, observed_generation = _header(
            response.headers,
            GENERATION_HEADER,
        )
        observed_generation = observed_generation.strip()
        if not generation_present or not observed_generation:
            raise ValueError(f"{label} is missing {GENERATION_HEADER}")
        if generation_id is not None and observed_generation != generation_id:
            raise ValueError(
                f"{label} generation {observed_generation!r} does not match "
                f"{generation_id!r}"
            )

        length_present, raw_length = _header(response.headers, "Content-Length")
        content_length: int | None = None
        if length_present:
            try:
                content_length = int(raw_length)
            except ValueError as exc:
                raise ValueError(f"{label} has invalid Content-Length") from exc
            if content_length <= 0 or content_length > MAXIMUM_MANIFEST_BYTES:
                raise ValueError(f"{label} has invalid Content-Length")

        digest = hashlib.sha256()
        size = 0
        body_parts: list[bytes] = []
        for chunk in response.iter_content(chunk_size=STREAM_CHUNK_BYTES):
            if not chunk:
                continue
            digest.update(chunk)
            body_parts.append(chunk)
            size += len(chunk)
            if size > MAXIMUM_MANIFEST_BYTES:
                raise ValueError(f"{label} exceeds the maximum permitted size")
        if size == 0:
            raise ValueError(f"{label} body is empty")
        if content_length is not None and size != content_length:
            raise ValueError(f"{label} streamed size does not match Content-Length")
        return (
            {
                "method": "GET",
                "url": url,
                "statusCode": 200,
                "contentLength": content_length,
                "sizeBytes": size,
                "sha256": digest.hexdigest(),
                "generationId": observed_generation,
            },
            b"".join(body_parts),
        )
    finally:
        response.close()


def _assert_review_required_artifact_handoff(
    artifact_handoff: Mapping[str, Any],
    *,
    expected: DownloadExpectation,
    expected_release_scope_sha256: str,
    base_url: str,
    label: str,
) -> None:
    if set(artifact_handoff) != REVIEW_REQUIRED_ARTIFACT_HANDOFF_KEYS:
        raise ValueError(f"{label} has an unexpected authority schema")
    public_install_route = str(
        artifact_handoff.get("publicInstallRoute") or ""
    ).strip()
    parsed_install_route = urlparse(public_install_route)
    if (
        not public_install_route.startswith("/downloads/install/")
        or parsed_install_route.scheme
        or parsed_install_route.netloc
        or parsed_install_route.params
        or parsed_install_route.query
        or parsed_install_route.fragment
    ):
        raise ValueError(
            f"{label} releaseTruth has an invalid withheld install route"
        )

    handoff_observed = {
        "contractName": str(
            artifact_handoff.get("contractName") or ""
        ).strip(),
        "status": str(artifact_handoff.get("status") or "").strip().lower(),
        "sourcePublicationState": str(
            artifact_handoff.get("sourcePublicationState") or ""
        ).strip().lower(),
        "releaseScopeDecisionSha256": _required_sha256(
            artifact_handoff,
            "releaseScopeDecisionSha256",
            f"{label} artifact handoff",
        ),
        "releaseVersion": str(
            artifact_handoff.get("releaseVersion") or ""
        ).strip(),
        "channel": str(
            artifact_handoff.get("channel") or ""
        ).strip().lower(),
        "artifactId": str(
            artifact_handoff.get("artifactId") or ""
        ).strip(),
        "platform": str(
            artifact_handoff.get("platform") or ""
        ).strip().lower(),
        "head": str(artifact_handoff.get("head") or "").strip(),
        "rid": str(artifact_handoff.get("rid") or "").strip(),
        "arch": str(artifact_handoff.get("arch") or "").strip(),
        "sha256": _required_sha256(
            artifact_handoff,
            "sha256",
            f"{label} artifact handoff",
        ),
        "sizeBytes": _required_size(
            artifact_handoff,
            "sizeBytes",
            f"{label} artifact handoff",
        ),
        "artifactAccessClass": str(
            artifact_handoff.get("artifactAccessClass") or ""
        ).strip().lower(),
        "signingRequirement": str(
            artifact_handoff.get("signingRequirement") or ""
        ).strip().lower(),
        "downloadUrl": _download_url(
            base_url,
            artifact_handoff.get("downloadUrl"),
            f"{label} artifact handoff",
        ),
    }
    handoff_required = {
        "contractName": "chummer.public-preview-byte-handoff/v1",
        "status": "approved_public_preview_bytes",
        "sourcePublicationState": "preview",
        "releaseScopeDecisionSha256": expected_release_scope_sha256,
        "releaseVersion": expected.release_version,
        "channel": "preview",
        "artifactId": expected.artifact_id,
        "platform": "windows",
        "head": expected.head,
        "rid": expected.rid,
        "arch": expected.arch,
        "sha256": expected.installer_sha256,
        "sizeBytes": expected.installer_size_bytes,
        "artifactAccessClass": "open_public",
        "signingRequirement": "preview_unsigned_allowed",
        "downloadUrl": expected.installer_url,
    }
    if handoff_observed != handoff_required:
        raise ValueError(
            f"{label} releaseTruth artifact handoff disagrees with the preview"
        )
    if public_install_route != f"/downloads/install/{expected.artifact_id}":
        raise ValueError(
            f"{label} withheld install route disagrees"
        )


def _release_evidence_roots(
    *,
    local_manifest_path: Path,
    local_canonical_manifest_path: Path,
    generation_id: str | None,
) -> list[Path]:
    generation_id = _safe_generation_segment(generation_id)
    roots: list[Path] = []
    for parent in dict.fromkeys(
        (
            local_manifest_path.parent,
            local_canonical_manifest_path.parent,
        )
    ):
        roots.extend(
            (
                parent / "release-evidence",
                parent / "bundle" / "release-evidence",
            )
        )
        if generation_id:
            roots.append(
                parent / "generations" / generation_id / "release-evidence"
            )
            if parent.name == "current":
                roots.append(
                    parent.parent
                    / "generations"
                    / generation_id
                    / "release-evidence"
                )
            if (
                parent.name == generation_id
                and parent.parent.name == "generations"
            ):
                roots.append(parent / "release-evidence")
    return list(dict.fromkeys(roots))


def _load_review_required_release_evidence(
    *,
    local_manifest_path: Path,
    local_canonical_manifest_path: Path,
    generation_id: str | None,
    expected: DownloadExpectation,
    expected_manifest_sha256: str,
    base_url: str,
) -> dict[str, Any]:
    evidence_names = (
        "CURRENT.json",
        "SNAPSHOT.json",
        "RELEASE_DECISION.json",
    )
    evidence_copies: list[tuple[bytes, bytes, bytes]] = []
    for root in _release_evidence_roots(
        local_manifest_path=local_manifest_path,
        local_canonical_manifest_path=local_canonical_manifest_path,
        generation_id=generation_id,
    ):
        paths = tuple(root / name for name in evidence_names)
        present = tuple(path.exists() or path.is_symlink() for path in paths)
        if not any(present):
            continue
        if not all(present):
            raise ValueError(
                f"local release evidence is incomplete: {root}"
            )
        evidence_copies.append(
            tuple(
                _regular_file_bytes(
                    path,
                    f"local release evidence {path.name}",
                )
                for path in paths
            )
        )
    if not evidence_copies:
        raise ValueError("local review-required release evidence is missing")
    if any(
        candidate != evidence_copies[0]
        for candidate in evidence_copies[1:]
    ):
        raise ValueError("local review-required release evidence copies disagree")

    current_bytes, snapshot_bytes, decision_bytes = evidence_copies[0]
    current = _json_object(current_bytes, "local release evidence CURRENT.json")
    snapshot = _json_object(
        snapshot_bytes,
        "local release evidence SNAPSHOT.json",
    )
    decision = _json_object(
        decision_bytes,
        "local release evidence RELEASE_DECISION.json",
    )
    snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
    decision_sha256 = hashlib.sha256(decision_bytes).hexdigest()
    if (
        _required_sha256(
            current,
            "snapshotSha256",
            "local release evidence CURRENT.json",
        )
        != snapshot_sha256
        or _required_sha256(
            current,
            "decisionSha256",
            "local release evidence CURRENT.json",
        )
        != decision_sha256
        or _required_text(
            current,
            "releaseVersion",
            "local release evidence CURRENT.json",
        )
        != expected.release_version
        or str(current.get("status") or "").strip().lower()
        != "review_required"
    ):
        raise ValueError("local release evidence CURRENT.json is not closed")

    registry_commit = _required_git_commit(
        snapshot,
        "registryCommit",
        "local release evidence SNAPSHOT.json",
    )
    known_issue_summary = _required_text(
        snapshot,
        "knownIssueSummary",
        "local release evidence SNAPSHOT.json",
    )
    snapshot_observed = {
        "authorityContract": str(
            snapshot.get("authorityContract") or ""
        ).strip(),
        "releaseVersion": str(
            snapshot.get("releaseVersion") or ""
        ).strip(),
        "channel": str(snapshot.get("channel") or "").strip().lower(),
        "status": str(snapshot.get("status") or "").strip().lower(),
        "rolloutState": str(
            snapshot.get("rolloutState") or ""
        ).strip().lower(),
        "supportabilityState": str(
            snapshot.get("supportabilityState") or ""
        ).strip().lower(),
        "downloadAccessPosture": str(
            snapshot.get("downloadAccessPosture") or ""
        ).strip().lower(),
        "releaseDecisionStatus": str(
            snapshot.get("releaseDecisionStatus") or ""
        ).strip().lower(),
        "manifestSha256": _required_sha256(
            snapshot,
            "manifestSha256",
            "local release evidence SNAPSHOT.json",
        ),
        "releaseDecisionSha256": _required_sha256(
            snapshot,
            "releaseDecisionSha256",
            "local release evidence SNAPSHOT.json",
        ),
        "artifactCount": _required_size(
            snapshot,
            "artifactCount",
            "local release evidence SNAPSHOT.json",
        ),
        "availablePlatforms": snapshot.get("availablePlatforms"),
        "primaryHeadByPlatform": snapshot.get(
            "primaryHeadByPlatform"
        ),
    }
    snapshot_required = {
        "authorityContract": "chummer.release-authority-snapshot/v2",
        "releaseVersion": expected.release_version,
        "channel": "preview",
        "status": "published",
        "rolloutState": "public_release_review_required",
        "supportabilityState": "review_required",
        "downloadAccessPosture": "open_public",
        "releaseDecisionStatus": "review_required",
        "manifestSha256": expected_manifest_sha256,
        "releaseDecisionSha256": decision_sha256,
        "artifactCount": 1,
        "availablePlatforms": ["windows"],
        "primaryHeadByPlatform": {"windows": expected.head},
    }
    if snapshot_observed != snapshot_required:
        raise ValueError(
            "local release evidence SNAPSHOT.json is not the expected authority"
        )
    snapshot_artifacts = _rows(
        snapshot,
        "artifacts",
        "local release evidence SNAPSHOT.json",
    )
    if len(snapshot_artifacts) != 1:
        raise ValueError(
            "local release evidence SNAPSHOT.json must bind one artifact"
        )
    snapshot_artifact = snapshot_artifacts[0]
    snapshot_artifact_observed = {
        "artifactId": str(
            snapshot_artifact.get("artifactId") or ""
        ).strip(),
        "head": str(snapshot_artifact.get("head") or "").strip(),
        "platform": str(
            snapshot_artifact.get("platform") or ""
        ).strip().lower(),
        "rid": str(snapshot_artifact.get("rid") or "").strip(),
        "arch": str(snapshot_artifact.get("arch") or "").strip(),
        "kind": str(snapshot_artifact.get("kind") or "").strip().lower(),
        "installAccessClass": str(
            snapshot_artifact.get("installAccessClass") or ""
        ).strip().lower(),
        "sha256": _required_sha256(
            snapshot_artifact,
            "sha256",
            "local release evidence snapshot artifact",
        ),
        "sizeBytes": _required_size(
            snapshot_artifact,
            "sizeBytes",
            "local release evidence snapshot artifact",
        ),
        "downloadUrl": _download_url(
            base_url,
            snapshot_artifact.get("downloadUrl"),
            "local release evidence snapshot artifact",
        ),
        "publicInstallRoute": str(
            snapshot_artifact.get("publicInstallRoute") or ""
        ).strip(),
    }
    snapshot_artifact_required = {
        "artifactId": expected.artifact_id,
        "head": expected.head,
        "platform": "windows",
        "rid": expected.rid,
        "arch": expected.arch,
        "kind": "installer",
        "installAccessClass": "open_public",
        "sha256": expected.installer_sha256,
        "sizeBytes": expected.installer_size_bytes,
        "downloadUrl": expected.installer_url,
        "publicInstallRoute": f"/downloads/install/{expected.artifact_id}",
    }
    if snapshot_artifact_observed != snapshot_artifact_required:
        raise ValueError(
            "local release evidence snapshot artifact disagrees with the preview"
        )

    decision_registry_commit = _required_git_commit(
        decision,
        "registryCommit",
        "local release evidence RELEASE_DECISION.json",
    )
    release_scope_sha256 = _required_sha256(
        decision,
        "releaseScopeDecisionSha256",
        "local release evidence RELEASE_DECISION.json",
    )
    decision_observed = {
        "contractName": str(decision.get("contractName") or "").strip(),
        "releaseVersion": str(
            decision.get("releaseVersion") or ""
        ).strip(),
        "channel": str(decision.get("channel") or "").strip().lower(),
        "status": str(decision.get("status") or "").strip().lower(),
        "releaseDecisionStatus": str(
            decision.get("releaseDecisionStatus") or ""
        ).strip().lower(),
        "verdict": str(decision.get("verdict") or "").strip(),
        "manifestSha256": _required_sha256(
            decision,
            "manifestSha256",
            "local release evidence RELEASE_DECISION.json",
        ),
        "artifactAccessClass": str(
            decision.get("artifactAccessClass") or ""
        ).strip().lower(),
        "platforms": decision.get("platforms"),
        "primaryHeadByPlatform": decision.get("primaryHeadByPlatform"),
    }
    decision_required = {
        "contractName": "chummer.preview-release-decision/v2",
        "releaseVersion": expected.release_version,
        "channel": "preview",
        "status": "review_required",
        "releaseDecisionStatus": "review_required",
        "verdict": "PREVIEW_RELEASE_REVIEW_REQUIRED",
        "manifestSha256": expected_manifest_sha256,
        "artifactAccessClass": "open_public",
        "platforms": ["windows"],
        "primaryHeadByPlatform": {"windows": expected.head},
    }
    if (
        decision_observed != decision_required
        or decision_registry_commit != registry_commit
    ):
        raise ValueError(
            "local release evidence RELEASE_DECISION.json is not the "
            "expected authority"
        )
    artifact_handoff = decision.get("artifactHandoff")
    if not isinstance(artifact_handoff, dict):
        raise ValueError(
            "local release evidence decision is missing artifactHandoff"
        )
    _assert_review_required_artifact_handoff(
        artifact_handoff,
        expected=expected,
        expected_release_scope_sha256=release_scope_sha256,
        base_url=base_url,
        label="local release evidence artifact handoff",
    )
    return {
        "registryCommit": registry_commit,
        "releaseDecisionSha256": decision_sha256,
        "releaseScopeDecisionSha256": release_scope_sha256,
        "artifactHandoff": artifact_handoff,
        "knownIssueSummary": known_issue_summary,
    }


def _assert_review_required_release_truth(
    payload: Mapping[str, Any],
    *,
    expected: DownloadExpectation,
    expected_manifest_sha256: str,
    expected_evidence: Mapping[str, Any],
    base_url: str,
    label: str,
) -> dict[str, Any]:
    release_truth = payload.get("releaseTruth")
    if not isinstance(release_truth, dict):
        raise ValueError(f"{label} is missing authenticated releaseTruth")
    if set(release_truth) != REVIEW_REQUIRED_RELEASE_TRUTH_KEYS:
        raise ValueError(
            f"{label} releaseTruth has an unexpected authority schema"
        )
    artifact_handoff = release_truth.get("artifactHandoff")
    if not isinstance(artifact_handoff, dict):
        raise ValueError(
            f"{label} releaseTruth is missing its artifact handoff"
        )

    release_scope_sha256 = _required_sha256(
        release_truth,
        "releaseScopeDecisionSha256",
        f"{label} releaseTruth",
    )
    release_decision_sha256 = _required_sha256(
        release_truth,
        "releaseDecisionSha256",
        f"{label} releaseTruth",
    )
    observed = {
        "contractName": str(release_truth.get("contractName") or "").strip(),
        "releaseVersion": str(
            release_truth.get("releaseVersion") or ""
        ).strip(),
        "channel": str(release_truth.get("channel") or "").strip().lower(),
        "releaseStatus": str(
            release_truth.get("releaseStatus") or ""
        ).strip().lower(),
        "rolloutState": str(
            release_truth.get("rolloutState") or ""
        ).strip().lower(),
        "supportabilityState": str(
            release_truth.get("supportabilityState") or ""
        ).strip().lower(),
        "downloadAccessPosture": str(
            release_truth.get("downloadAccessPosture") or ""
        ).strip().lower(),
        "releaseDecisionStatus": str(
            release_truth.get("releaseDecisionStatus") or ""
        ).strip().lower(),
        "manifestSha256": _required_sha256(
            release_truth,
            "manifestSha256",
            f"{label} releaseTruth",
        ),
        "registryCommit": _required_git_commit(
            release_truth,
            "registryCommit",
            f"{label} releaseTruth",
        ),
        "artifactCount": _required_size(
            release_truth,
            "artifactCount",
            f"{label} releaseTruth",
        ),
        "availablePlatforms": release_truth.get("availablePlatforms"),
        "primaryHeadByPlatform": release_truth.get(
            "primaryHeadByPlatform"
        ),
        "knownIssueSummary": _required_text(
            release_truth,
            "knownIssueSummary",
            f"{label} releaseTruth",
        ),
        "releaseDecisionSha256": release_decision_sha256,
        "releaseScopeDecisionSha256": release_scope_sha256,
    }
    required = {
        "contractName": "chummer.release-truth-projection/v1",
        "releaseVersion": expected.release_version,
        "channel": "preview",
        "releaseStatus": "published",
        "rolloutState": "public_release_review_required",
        "supportabilityState": "review_required",
        "downloadAccessPosture": "open_public",
        "releaseDecisionStatus": "review_required",
        "manifestSha256": expected_manifest_sha256,
        "registryCommit": expected_evidence["registryCommit"],
        "artifactCount": 1,
        "availablePlatforms": ["windows"],
        "primaryHeadByPlatform": {"windows": expected.head},
        "knownIssueSummary": expected_evidence["knownIssueSummary"],
        "releaseDecisionSha256": expected_evidence[
            "releaseDecisionSha256"
        ],
        "releaseScopeDecisionSha256": expected_evidence[
            "releaseScopeDecisionSha256"
        ],
    }
    if observed != required:
        raise ValueError(
            f"{label} releaseTruth is not the expected review-required authority"
        )
    _assert_review_required_artifact_handoff(
        artifact_handoff,
        expected=expected,
        expected_release_scope_sha256=release_scope_sha256,
        base_url=base_url,
        label=f"{label} releaseTruth artifact handoff",
    )
    if artifact_handoff != expected_evidence["artifactHandoff"]:
        raise ValueError(
            f"{label} releaseTruth artifact handoff is not evidence-bound"
        )
    return release_truth


def _validate_live_canonical_manifest(
    payload: Mapping[str, Any],
    expectations: list[DownloadExpectation],
    generation_id: str,
    base_url: str,
) -> None:
    embedded_generation = str(payload.get("generationId") or "").strip()
    if embedded_generation and embedded_generation != generation_id:
        raise ValueError("live canonical manifest generationId disagrees with its header")
    live_rows = {
        str(row.get("artifactId") or row.get("id") or "").strip(): row
        for row in _rows(payload, "artifacts", "live canonical manifest")
    }
    for expected in expectations:
        artifact = live_rows.get(expected.artifact_id)
        if artifact is None:
            raise ValueError(
                f"live canonical manifest is missing {expected.artifact_id}"
            )
        _assert_manifest_policy(payload, artifact)
        observed = {
            "version": str(
                artifact.get("version") or artifact.get("releaseVersion") or ""
            ).strip(),
            "installerFileName": str(artifact.get("fileName") or "").strip(),
            "installerUrl": _download_url(
                base_url,
                artifact.get("downloadUrl") or artifact.get("url"),
                f"live {expected.artifact_id} installer",
            ),
            "installerSha256": str(artifact.get("sha256") or "").strip().lower(),
            "installerSizeBytes": int(artifact.get("sizeBytes") or 0),
            "payloadFileName": str(artifact.get("payloadFileName") or "").strip(),
            "manifestPayloadUrl": _download_url(
                base_url,
                artifact.get("payloadDownloadUrl"),
                f"live {expected.artifact_id} payload",
            ),
            "payloadSha256": str(artifact.get("payloadSha256") or "").strip().lower(),
            "payloadSizeBytes": int(artifact.get("payloadSizeBytes") or 0),
        }
        required = {
            "version": expected.release_version,
            "installerFileName": expected.installer_file_name,
            "installerUrl": expected.installer_url,
            "installerSha256": expected.installer_sha256,
            "installerSizeBytes": expected.installer_size_bytes,
            "payloadFileName": expected.payload_file_name,
            "manifestPayloadUrl": expected.manifest_payload_url,
            "payloadSha256": expected.payload_sha256,
            "payloadSizeBytes": expected.payload_size_bytes,
        }
        if observed != required:
            raise ValueError(
                f"live canonical manifest metadata disagrees for {expected.artifact_id}"
            )


def _validate_embedded_installer_metadata(
    installer_bytes: bytes,
    expected: DownloadExpectation,
) -> None:
    required = {
        "payloadDownloadUrl label": b"payloadDownloadUrl",
        "payloadSha256 label": b"payloadSha256",
        "payloadSizeBytes label": b"payloadSizeBytes",
        "payloadDownloadUrl value": expected.payload_url.encode("utf-8"),
        "payloadSha256 value": expected.payload_sha256.encode("ascii"),
        "payloadSizeBytes value": str(expected.payload_size_bytes).encode("ascii"),
    }
    for label, value in required.items():
        if value not in installer_bytes:
            raise ValueError(f"bootstrap installer is missing embedded {label}")


def verify_public_download_delivery(
    *,
    session: requests.Session,
    delivery_phase: str,
    base_url: str,
    local_manifest_path: Path,
    local_canonical_manifest_path: Path,
    timeout: float,
) -> dict[str, Any]:
    base = _validated_base_url(base_url)
    local_canonical_bytes = _regular_file_bytes(
        local_canonical_manifest_path,
        "local canonical manifest",
    )
    local_compatibility_bytes = _regular_file_bytes(
        local_manifest_path,
        "local compatibility manifest",
    )
    local_canonical = _json_object(
        local_canonical_bytes,
        "local canonical manifest",
    )
    local_compatibility = _json_object(
        local_compatibility_bytes,
        "local compatibility manifest",
    )
    _require_delivery_phase_shape(
        delivery_phase=delivery_phase,
        canonical=local_canonical,
        compatibility=local_compatibility,
    )
    canonical_generation = str(local_canonical.get("generationId") or "").strip()
    compatibility_generation = str(
        local_compatibility.get("generationId") or ""
    ).strip()
    if (
        canonical_generation
        and compatibility_generation
        and canonical_generation != compatibility_generation
    ):
        raise ValueError("local manifest generation ids disagree")
    expected_generation = (
        canonical_generation or compatibility_generation or None
    )

    canonical_receipt, live_canonical_bytes = _stream_manifest_get(
        session=session,
        url=f"{base}/downloads/RELEASE_CHANNEL.generated.json",
        label="canonical manifest",
        timeout=timeout,
        generation_id=expected_generation,
    )
    generation_id = canonical_receipt["generationId"]
    compatibility_receipt, live_compatibility_bytes = _stream_manifest_get(
        session=session,
        url=f"{base}/downloads/releases.json",
        label="compatibility manifest",
        timeout=timeout,
        generation_id=generation_id,
    )
    canonical_receipt.update(
        {
            "localSha256": hashlib.sha256(local_canonical_bytes).hexdigest(),
            "localSizeBytes": len(local_canonical_bytes),
        }
    )
    compatibility_receipt.update(
        {
            "localSha256": hashlib.sha256(
                local_compatibility_bytes
            ).hexdigest(),
            "localSizeBytes": len(local_compatibility_bytes),
        }
    )
    live_canonical = _json_object(live_canonical_bytes, "live canonical manifest")
    live_compatibility = _json_object(
        live_compatibility_bytes,
        "live compatibility manifest",
    )
    _require_delivery_phase_shape(
        delivery_phase=delivery_phase,
        canonical=live_canonical,
        compatibility=live_compatibility,
    )

    expectations: list[DownloadExpectation] = []
    release_truth_sha256: str | None = None
    if delivery_phase == DELIVERY_PHASE_WINDOWS_PREVIEW:
        _canonical_bytes, _generation, expectations = (
            derive_download_expectations(
                base_url=base,
                local_manifest_path=local_manifest_path,
                local_canonical_manifest_path=local_canonical_manifest_path,
            )
        )
        if len(expectations) != 1:
            raise ValueError(
                "Windows preview releaseTruth requires exactly one artifact"
            )
        served_canonical = dict(live_canonical)
        served_canonical.pop("releaseTruth", None)
        if served_canonical != local_canonical:
            raise ValueError(
                "live canonical manifest changed sealed fields outside releaseTruth"
            )
        served_compatibility = dict(live_compatibility)
        served_compatibility.pop("releaseTruth", None)
        if served_compatibility != local_compatibility:
            raise ValueError(
                "live compatibility manifest changed sealed fields outside releaseTruth"
            )
        expected_manifest_sha256 = hashlib.sha256(
            local_canonical_bytes
        ).hexdigest()
        expected_evidence = _load_review_required_release_evidence(
            local_manifest_path=local_manifest_path,
            local_canonical_manifest_path=local_canonical_manifest_path,
            generation_id=generation_id,
            expected=expectations[0],
            expected_manifest_sha256=expected_manifest_sha256,
            base_url=base,
        )
        canonical_release_truth = _assert_review_required_release_truth(
            live_canonical,
            expected=expectations[0],
            expected_manifest_sha256=expected_manifest_sha256,
            expected_evidence=expected_evidence,
            base_url=base,
            label="live canonical manifest",
        )
        compatibility_release_truth = _assert_review_required_release_truth(
            live_compatibility,
            expected=expectations[0],
            expected_manifest_sha256=expected_manifest_sha256,
            expected_evidence=expected_evidence,
            base_url=base,
            label="live compatibility manifest",
        )
        if canonical_release_truth != compatibility_release_truth:
            raise ValueError(
                "live canonical and compatibility releaseTruth disagree"
            )
        release_truth_sha256 = _canonical_object_sha256(
            canonical_release_truth
        )
        _validate_live_canonical_manifest(
            live_canonical,
            expectations,
            generation_id,
            base,
        )

    artifact_receipts: list[dict[str, Any]] = []
    for expected in expectations:
        installer_receipt, installer_bytes = _stream_exact_get(
            session=session,
            url=expected.installer_url,
            label=f"{expected.artifact_id} installer",
            expected_sha256=expected.installer_sha256,
            expected_size_bytes=expected.installer_size_bytes,
            timeout=timeout,
            generation_id=generation_id,
            capture=True,
        )
        payload_receipt, _ = _stream_exact_get(
            session=session,
            url=expected.payload_probe_url,
            label=f"{expected.artifact_id} payload",
            expected_sha256=expected.payload_sha256,
            expected_size_bytes=expected.payload_size_bytes,
            timeout=timeout,
            generation_id=generation_id,
            capture=False,
        )
        sidecar_receipt, sidecar_bytes = _stream_exact_get(
            session=session,
            url=expected.sidecar_probe_url,
            label=f"{expected.artifact_id} sidecar",
            expected_sha256=expected.sidecar_sha256,
            expected_size_bytes=expected.sidecar_size_bytes,
            timeout=timeout,
            generation_id=generation_id,
            capture=True,
        )
        _validate_sidecar(
            _json_object(sidecar_bytes, f"live {expected.sidecar_file_name}"),
            expected,
        )
        _validate_embedded_installer_metadata(installer_bytes, expected)
        artifact_receipts.append(
            {
                "artifactId": expected.artifact_id,
                "releaseVersion": expected.release_version,
                "policy": {
                    "channel": "preview",
                    "supportabilityState": "review_required",
                    "installAccessClass": "open_public",
                    "artifactByteVisibility": "public",
                    "signatureStatus": "unsigned",
                    "signaturePolicy": "preview_policy",
                    "publicInstallRoute": None,
                    "stable": False,
                    "update": False,
                },
                "installer": installer_receipt,
                "payload": payload_receipt,
                "sidecar": sidecar_receipt,
                "embeddedInstallerMetadataAgrees": True,
            }
        )

    return {
        "status": "pass",
        "deliveryPhase": delivery_phase,
        "expectedWindowsState": (
            "absent"
            if delivery_phase == DELIVERY_PHASE_BOOTSTRAP
            else "present"
        ),
        "windowsDeliveryClaimed": (
            delivery_phase == DELIVERY_PHASE_WINDOWS_PREVIEW
        ),
        "generationHeader": GENERATION_HEADER,
        "generationId": generation_id,
        "canonicalManifest": canonical_receipt,
        "compatibilityManifest": compatibility_receipt,
        "releaseTruthSha256": release_truth_sha256,
        "artifacts": artifact_receipts,
    }


def verify_control_plane(
    session: requests.Session,
    base_url: str,
    timeout: float,
) -> dict[str, Any]:
    serving = get(session, base_url, "/api/ready/public-downloads", timeout)
    _reject_credential_headers(serving, "public downloads readiness")
    serving_payload = require_json(serving, "public downloads readiness")
    checks = serving_payload.get("checks")
    release_shelf = serving_payload.get("releaseShelf")
    if (
        serving.status_code != 200
        or serving_payload.get("contractName") != READINESS_CONTRACT
        or serving_payload.get("ready") is not True
        or serving_payload.get("status") != "pass"
        or serving_payload.get("servingReady") is not True
        or serving_payload.get("overallReady") is not False
        or serving_payload.get("overallStatus") != "fail"
        or serving_payload.get("publicationReady") is not False
        or not isinstance(checks, list)
        or not isinstance(release_shelf, dict)
        or release_shelf.get("servingReady") is not True
    ):
        raise ValueError("public downloads readiness contract is not serving-only")

    readiness_statuses: dict[str, int] = {}
    for path in UNAVAILABLE_READINESS_PATHS:
        response = get(session, base_url, path, timeout)
        _reject_credential_headers(response, path)
        readiness_statuses[path] = response.status_code
        if response.status_code != 503:
            raise ValueError(f"{path} unexpectedly claimed readiness")

    private_statuses: dict[str, int] = {}
    for path in PRIVATE_PATHS:
        response = get(session, base_url, path, timeout)
        _reject_credential_headers(response, path)
        private_statuses[path] = response.status_code
        if (
            response.status_code != 503
            or _media_type(response.headers) != "application/problem+json"
            or response.headers.get("Cache-Control")
            != "private, no-store, max-age=0"
            or response.headers.get("Pragma") != "no-cache"
            or response.headers.get("Expires") != "0"
            or require_json(response, path) != PROBLEM
        ):
            raise ValueError(f"{path} did not enforce the private 503 boundary")

    install_route_denial_statuses: dict[str, int] = {}
    install_route_release_truth_sha256: str | None = None
    install_route_paths = list(INSTALL_ROUTE_DENIAL_PATHS)
    route_index = 0
    while route_index < len(install_route_paths):
        path = install_route_paths[route_index]
        route_index += 1
        response = get(session, base_url, path, timeout)
        _reject_credential_headers(response, path)
        install_route_denial_statuses[path] = response.status_code
        payload = require_json(response, path)
        release_truth = payload.get("releaseTruth")
        if (
            set(payload) != {"message", "releaseTruth", "status"}
            or not isinstance(release_truth, dict)
            or set(release_truth) != REVIEW_REQUIRED_RELEASE_TRUTH_KEYS
            or not isinstance(release_truth.get("artifactHandoff"), dict)
            or set(release_truth["artifactHandoff"])
            != REVIEW_REQUIRED_ARTIFACT_HANDOFF_KEYS
        ):
            raise ValueError(
                f"{path} did not enforce the review-required install denial"
            )
        artifact_handoff = release_truth["artifactHandoff"]
        artifact_id = str(
            artifact_handoff.get("artifactId") or ""
        ).strip()
        advertised_install_route = str(
            artifact_handoff.get("publicInstallRoute") or ""
        ).strip()
        if (
            not artifact_id
            or len(artifact_id) > 128
            or not (
                artifact_id[0].isascii()
                and (
                    artifact_id[0].islower()
                    or artifact_id[0].isdigit()
                )
            )
            or any(
                not (
                    character.isascii()
                    and (
                        character.islower()
                        or character.isdigit()
                        or character == "-"
                    )
                )
                for character in artifact_id
            )
            or advertised_install_route
            != f"/downloads/install/{artifact_id}"
        ):
            raise ValueError(
                f"{path} advertised an unsafe or unbound publicInstallRoute"
            )
        if advertised_install_route not in install_route_paths:
            install_route_paths.append(advertised_install_route)
        release_truth_sha256 = _canonical_object_sha256(release_truth)
        if (
            install_route_release_truth_sha256 is not None
            and install_route_release_truth_sha256
            != release_truth_sha256
        ):
            raise ValueError(
                "install denial routes disagree on releaseTruth"
            )
        install_route_release_truth_sha256 = release_truth_sha256
        if (
            response.status_code != 409
            or _media_type(response.headers) != "application/json"
            or response.headers.get("Cache-Control")
            != "private, no-store, max-age=0"
            or response.headers.get("Pragma") != "no-cache"
            or response.headers.get("Expires") != "0"
            or payload.get("status") != "review_required"
            or not str(payload.get("message") or "").strip()
            or release_truth.get("contractName")
            != "chummer.release-truth-projection/v1"
            or release_truth.get("channel") != "preview"
            or release_truth.get("supportabilityState") != "review_required"
            or release_truth.get("rolloutState")
            != "public_release_review_required"
            or release_truth.get("downloadAccessPosture") != "open_public"
            or release_truth.get("releaseStatus") != "published"
            or release_truth.get("releaseDecisionStatus")
            != "review_required"
            or release_truth.get("availablePlatforms") != ["windows"]
            or release_truth.get("artifactCount") != 1
            or not str(release_truth.get("releaseVersion") or "").strip()
            or not str(release_truth.get("knownIssueSummary") or "").strip()
        ):
            raise ValueError(
                f"{path} did not enforce the review-required install denial"
            )
    return {
        "servingReadiness": serving_payload,
        "unavailableReadinessStatuses": readiness_statuses,
        "privateBoundaryStatuses": private_statuses,
        "installRouteDenialStatuses": install_route_denial_statuses,
        "installRouteReleaseTruthSha256": (
            install_route_release_truth_sha256
        ),
    }


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ValueError("postdeploy output must be new")
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--local-manifest", type=Path, required=True)
    parser.add_argument("--local-canonical-manifest", type=Path, required=True)
    parser.add_argument(
        "--delivery-phase",
        choices=DELIVERY_PHASES,
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        with anonymous_session() as session:
            control_plane = verify_control_plane(
                session,
                args.base_url,
                args.timeout,
            )
            truth_gate = load_truth_gate(args.source_root)
            truth_gate.requests = AnonymousRequestsAdapter(session)
            download_truth = truth_gate.evaluate(
                base_url=args.base_url,
                local_manifest_path=args.local_manifest,
                local_canonical_manifest_path=args.local_canonical_manifest,
                timeout=args.timeout,
                artifact_probes_enabled=False,
                live_confirmation_count=3,
                live_confirmation_delay_seconds=2.0,
                live_max_samples=6,
                page_artifact_alignment_required=False,
            )
            if download_truth.get("status") != "pass":
                raise ValueError("public download shelf truth gate failed")
            strict_downloads = verify_public_download_delivery(
                session=session,
                delivery_phase=args.delivery_phase,
                base_url=args.base_url,
                local_manifest_path=args.local_manifest,
                local_canonical_manifest_path=args.local_canonical_manifest,
                timeout=args.timeout,
            )
            if (
                args.delivery_phase == DELIVERY_PHASE_WINDOWS_PREVIEW
                and control_plane.get(
                    "installRouteReleaseTruthSha256"
                )
                != strict_downloads.get("releaseTruthSha256")
            ):
                raise ValueError(
                    "install denial releaseTruth disagrees with the "
                    "authenticated manifests"
                )
        payload = {
            "contractName": CONTRACT_NAME,
            "status": "pass",
            "runtimeProfile": "public-download-only",
            "deliveryPhase": args.delivery_phase,
            "baseUrl": args.base_url.rstrip("/"),
            **control_plane,
            "publicDownloadTruth": download_truth,
            "strictPublicDownloads": strict_downloads,
        }
        atomic_write(args.output, payload)
    except (OSError, requests.RequestException, ValueError) as exc:
        print(f"public_download_only_postdeploy: {exc}", file=sys.stderr)
        return 1
    print("public_download_only_postdeploy:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
