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
from urllib.parse import ParseResult, urljoin, urlparse

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


class DownloadExpectation(NamedTuple):
    artifact_id: str
    release_version: str
    installer_file_name: str
    installer_url: str
    installer_sha256: str
    installer_size_bytes: int
    payload_file_name: str
    payload_url: str
    payload_sha256: str
    payload_size_bytes: int
    sidecar_file_name: str
    sidecar_url: str
    sidecar_sha256: str
    sidecar_size_bytes: int
    sidecar_bytes: bytes


class AnonymousAuth(requests.auth.AuthBase):
    """Prevent requests/netrc from attaching ambient credentials."""

    def __call__(self, request: requests.PreparedRequest) -> requests.PreparedRequest:
        for header in CREDENTIAL_REQUEST_HEADERS:
            request.headers.pop(header, None)
        return request


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


def anonymous_get(url: str, timeout: float, *, stream: bool) -> requests.Response:
    return requests.get(
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


def get(base_url: str, path: str, timeout: float) -> requests.Response:
    return requests.get(
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


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} is not a JSON object")
    return payload


def _regular_file_bytes(path: Path, label: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is not a regular local file: {path}")
    return path.read_bytes()


def _find_sidecar_bytes(
    local_manifest_path: Path,
    local_canonical_manifest_path: Path,
    sidecar_file_name: str,
) -> bytes:
    roots = (
        local_manifest_path.parent / "files",
        local_canonical_manifest_path.parent / "files",
        local_manifest_path.parent / "bundle" / "files",
        local_canonical_manifest_path.parent / "bundle" / "files",
    )
    matches: list[bytes] = []
    for root in roots:
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
    if str(artifact.get("artifactByteVisibility") or "").strip().lower() != "public":
        raise ValueError(f"{artifact_id} byte visibility is not public")
    if str(artifact.get("installerMode") or "").strip().lower() != "bootstrap":
        raise ValueError(f"{artifact_id} is not a bootstrap installer")
    if str(artifact.get("payloadAcquisitionMode") or "").strip().lower() != "download":
        raise ValueError(f"{artifact_id} payload acquisition is not download")
    if str(artifact.get("previewPolicy") or "").strip().lower() != "preview_policy":
        raise ValueError(f"{artifact_id} preview policy is invalid")
    if artifact.get("publicInstallRoute") is not None:
        raise ValueError(f"{artifact_id} unexpectedly claims a public install route")
    if any(artifact.get(key) is True for key in ("stable", "stableEligible", "update", "updateEligible")):
        raise ValueError(f"{artifact_id} unexpectedly claims stable/update eligibility")
    if str(artifact.get("version") or artifact.get("releaseVersion") or "").strip() != version:
        raise ValueError(f"{artifact_id} release version disagrees with the manifest")

    signature = artifact.get("signature")
    if not isinstance(signature, dict) or (
        str(signature.get("status") or "").strip().lower() != "unsigned"
        or str(signature.get("policy") or "").strip().lower() != "preview_policy"
        or signature.get("required") is not False
    ):
        raise ValueError(f"{artifact_id} is not unsigned under preview_policy")

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
    promotion = str(route.get("promotionState") or "").strip().lower()
    update = str(route.get("updateEligibility") or "").strip().lower()
    if (
        route.get("publicInstallRoute") is not None
        or route.get("routeAuthority") is not False
        or str(route.get("publicationState") or "").strip().lower() != "preview"
        or str(route.get("visibility") or "").strip().lower() != "public_artifact_only"
        or promotion in {"promoted", "public_stable", "stable"}
        or not promotion
    ):
        raise ValueError(f"{artifact_id} route truth unexpectedly claims stable/install authority")
    if update in {"eligible", "automatic", "auto", "auto_update", "enabled", "true"} or not update:
        raise ValueError(f"{artifact_id} route truth unexpectedly claims update eligibility")


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
    parsed_download_url = urlparse(raw_download_url)
    if parsed_download_url.scheme.lower() != "https" or not parsed_download_url.hostname:
        raise ValueError("bootstrap sidecar downloadUrl is not absolute HTTPS")
    if _download_url(
        expected.installer_url,
        raw_download_url,
        "bootstrap sidecar payload",
    ) != expected.payload_url:
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

    canonical_rows = [
        row
        for row in _rows(canonical, "artifacts", "local canonical manifest")
        if _row_platform_is_windows(row)
        and str(row.get("kind") or "").strip().lower() == "installer"
        and str(row.get("installerMode") or "").strip().lower() == "bootstrap"
    ]
    if not canonical_rows:
        raise ValueError("canonical manifest has no Windows bootstrap installer")

    compatibility_by_id = {
        str(row.get("artifactId") or row.get("id") or "").strip(): row
        for row in _rows(compatibility, "downloads", "local compatibility manifest")
    }
    expectations: list[DownloadExpectation] = []
    version = _required_text(canonical, "version", "canonical manifest")
    for artifact in canonical_rows:
        _assert_manifest_policy(canonical, artifact)
        artifact_id = _required_text(artifact, "artifactId", "Windows artifact")
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
        payload_url = _download_url(
            base,
            artifact.get("payloadDownloadUrl"),
            f"{artifact_id} payload",
        )
        if Path(urlparse(installer_url).path).name != installer_file_name:
            raise ValueError(f"{artifact_id} installer URL filename disagrees with manifest")
        if Path(urlparse(payload_url).path).name != payload_file_name:
            raise ValueError(f"{artifact_id} payload URL filename disagrees with manifest")

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
            "payload_url": _download_url(
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
            "payload_url": payload_url,
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
        )
        expectation = DownloadExpectation(
            artifact_id=artifact_id,
            release_version=version,
            installer_file_name=installer_file_name,
            installer_url=installer_url,
            installer_sha256=installer_sha256,
            installer_size_bytes=installer_size,
            payload_file_name=payload_file_name,
            payload_url=payload_url,
            payload_sha256=payload_sha256,
            payload_size_bytes=payload_size,
            sidecar_file_name=sidecar_file_name,
            sidecar_url=_sidecar_url(payload_url),
            sidecar_sha256=hashlib.sha256(sidecar_bytes).hexdigest(),
            sidecar_size_bytes=len(sidecar_bytes),
            sidecar_bytes=sidecar_bytes,
        )
        _validate_sidecar(
            _json_object(sidecar_bytes, f"local {sidecar_file_name}"),
            expectation,
        )
        expectations.append(expectation)
    return canonical_bytes, expected_generation, expectations


def _stream_exact_get(
    *,
    url: str,
    label: str,
    expected_sha256: str,
    expected_size_bytes: int,
    timeout: float,
    generation_id: str | None,
    capture: bool,
) -> tuple[dict[str, Any], bytes]:
    response = anonymous_get(url, timeout, stream=True)
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


def _stream_canonical_manifest_get(
    *,
    url: str,
    timeout: float,
    generation_id: str | None,
) -> tuple[dict[str, Any], bytes]:
    label = "canonical manifest"
    response = anonymous_get(url, timeout, stream=True)
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
            "payloadUrl": _download_url(
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
            "payloadUrl": expected.payload_url,
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
    base_url: str,
    local_manifest_path: Path,
    local_canonical_manifest_path: Path,
    timeout: float,
) -> dict[str, Any]:
    base = _validated_base_url(base_url)
    _canonical_bytes, expected_generation, expectations = derive_download_expectations(
        base_url=base,
        local_manifest_path=local_manifest_path,
        local_canonical_manifest_path=local_canonical_manifest_path,
    )
    manifest_receipt, live_canonical_bytes = _stream_canonical_manifest_get(
        url=f"{base}/downloads/RELEASE_CHANNEL.generated.json",
        timeout=timeout,
        generation_id=expected_generation,
    )
    generation_id = manifest_receipt["generationId"]
    live_canonical = _json_object(live_canonical_bytes, "live canonical manifest")
    _validate_live_canonical_manifest(
        live_canonical,
        expectations,
        generation_id,
        base,
    )

    artifact_receipts: list[dict[str, Any]] = []
    for expected in expectations:
        installer_receipt, installer_bytes = _stream_exact_get(
            url=expected.installer_url,
            label=f"{expected.artifact_id} installer",
            expected_sha256=expected.installer_sha256,
            expected_size_bytes=expected.installer_size_bytes,
            timeout=timeout,
            generation_id=generation_id,
            capture=True,
        )
        payload_receipt, _ = _stream_exact_get(
            url=expected.payload_url,
            label=f"{expected.artifact_id} payload",
            expected_sha256=expected.payload_sha256,
            expected_size_bytes=expected.payload_size_bytes,
            timeout=timeout,
            generation_id=generation_id,
            capture=False,
        )
        sidecar_receipt, sidecar_bytes = _stream_exact_get(
            url=expected.sidecar_url,
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
        "generationHeader": GENERATION_HEADER,
        "generationId": generation_id,
        "canonicalManifest": manifest_receipt,
        "artifacts": artifact_receipts,
    }


def verify_control_plane(base_url: str, timeout: float) -> dict[str, Any]:
    serving = get(base_url, "/api/ready/public-downloads", timeout)
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
        response = get(base_url, path, timeout)
        _reject_credential_headers(response, path)
        readiness_statuses[path] = response.status_code
        if response.status_code != 503:
            raise ValueError(f"{path} unexpectedly claimed readiness")

    private_statuses: dict[str, int] = {}
    for path in PRIVATE_PATHS:
        response = get(base_url, path, timeout)
        _reject_credential_headers(response, path)
        private_statuses[path] = response.status_code
        content_type = response.headers.get("Content-Type", "").lower()
        if (
            response.status_code != 503
            or not content_type.startswith("application/problem+json")
            or response.headers.get("Cache-Control")
            != "private, no-store, max-age=0"
            or response.headers.get("Pragma") != "no-cache"
            or response.headers.get("Expires") != "0"
            or require_json(response, path) != PROBLEM
        ):
            raise ValueError(f"{path} did not enforce the private 503 boundary")
    return {
        "servingReadiness": serving_payload,
        "unavailableReadinessStatuses": readiness_statuses,
        "privateBoundaryStatuses": private_statuses,
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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        control_plane = verify_control_plane(args.base_url, args.timeout)
        truth_gate = load_truth_gate(args.source_root)
        download_truth = truth_gate.evaluate(
            base_url=args.base_url,
            local_manifest_path=args.local_manifest,
            local_canonical_manifest_path=args.local_canonical_manifest,
            timeout=args.timeout,
            artifact_probes_enabled=False,
            live_confirmation_count=3,
            live_confirmation_delay_seconds=2.0,
            live_max_samples=6,
        )
        if download_truth.get("status") != "pass":
            raise ValueError("public download shelf truth gate failed")
        strict_downloads = verify_public_download_delivery(
            base_url=args.base_url,
            local_manifest_path=args.local_manifest,
            local_canonical_manifest_path=args.local_canonical_manifest,
            timeout=args.timeout,
        )
        payload = {
            "contractName": CONTRACT_NAME,
            "status": "pass",
            "runtimeProfile": "public-download-only",
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
