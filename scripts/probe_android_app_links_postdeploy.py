#!/usr/bin/env python3
"""Read-only post-deploy probe for Chummer's Android App Links association file.

This validates the served association bytes only; it does not evaluate device state.
"""

from __future__ import annotations

import hashlib
import json
import stat
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)


CONTRACT_NAME = "chummer.android.digital_asset_links_postdeploy/v1"
ASSET_LINKS_URL = "https://chummer.run/.well-known/assetlinks.json"
TRACKED_ASSET_LINKS = (
    Path(__file__).resolve().parents[1]
    / "Chummer.Run.Api"
    / "wwwroot"
    / ".well-known"
    / "assetlinks.json"
)
USER_AGENT = "ChummerAndroidAppLinksPostdeploy/1.0"
REQUEST_TIMEOUT_SECONDS = 20
MAXIMUM_RESPONSE_BYTES = 64 * 1024


class AppLinksProbeFailure(RuntimeError):
    """Fail-closed probe outcome with a stable, non-secret reason."""


@dataclass(frozen=True)
class AppLinksProbeResult:
    contract_name: str
    status: str
    url: str
    final_url: str
    http_status: int
    content_type: str
    payload_sha256: str
    association_file_matches: bool
    device_verification_evaluated: bool


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        del request, file_pointer, code, message, headers, new_url
        return None


def _strict_json_array(raw: bytes, *, label: str) -> list[Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    def reject_non_finite(value: str) -> None:
        raise ValueError(f"{label} contains non-finite JSON number {value}")

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_non_finite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise AppLinksProbeFailure(f"{label}_invalid_json") from exc
    if not isinstance(payload, list):
        raise AppLinksProbeFailure(f"{label}_not_array")
    return payload


def _read_bounded(stream: Any, *, label: str) -> bytes:
    payload = stream.read(MAXIMUM_RESPONSE_BYTES + 1)
    if len(payload) > MAXIMUM_RESPONSE_BYTES:
        raise AppLinksProbeFailure(f"{label}_too_large")
    return payload


def _read_tracked_asset_links(path: Path) -> bytes:
    try:
        file_status = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(file_status.st_mode):
            raise AppLinksProbeFailure("tracked_assetlinks_not_regular_file")
        payload = path.read_bytes()
    except AppLinksProbeFailure:
        raise
    except OSError as exc:
        raise AppLinksProbeFailure("tracked_assetlinks_unavailable") from exc
    if len(payload) > MAXIMUM_RESPONSE_BYTES:
        raise AppLinksProbeFailure("tracked_assetlinks_too_large")
    return payload


def _content_type(headers: Any) -> str:
    for name, value in headers.items():
        if name.lower() == "content-type":
            return str(value).split(";", 1)[0].strip().lower()
    return ""


def _is_cloudflare_1033(status_code: int, payload: bytes) -> bool:
    text = payload.decode("utf-8", errors="replace").lower()
    return status_code == 530 and (
        "error code: 1033" in text
        or ("cloudflare tunnel error" in text and "1033" in text)
    )


def _open_without_redirects(request: Request, timeout: int) -> Any:
    opener = build_opener(ProxyHandler({}), NoRedirectHandler())
    return opener.open(request, timeout=timeout)


def probe_android_app_links(
    open_url: Callable[[Request, int], Any] = _open_without_redirects,
    tracked_path: Path = TRACKED_ASSET_LINKS,
) -> AppLinksProbeResult:
    tracked_bytes = _read_tracked_asset_links(tracked_path)
    tracked_payload = _strict_json_array(tracked_bytes, label="tracked_assetlinks")
    request = Request(
        ASSET_LINKS_URL,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )

    try:
        with open_url(request, REQUEST_TIMEOUT_SECONDS) as response:
            status_code = response.getcode()
            final_url = response.geturl()
            headers = response.headers
            live_bytes = _read_bounded(response, label="live_assetlinks")
    except HTTPError as exc:
        error_bytes = _read_bounded(exc, label="live_error_response")
        if 300 <= exc.code < 400:
            raise AppLinksProbeFailure("redirect_forbidden") from exc
        if _is_cloudflare_1033(exc.code, error_bytes):
            raise AppLinksProbeFailure("cloudflare_1033_origin_unreachable") from exc
        raise AppLinksProbeFailure(f"unexpected_http_status_{exc.code}") from exc
    except AppLinksProbeFailure:
        raise
    except OSError as exc:
        raise AppLinksProbeFailure("public_origin_unreachable") from exc

    if final_url != ASSET_LINKS_URL:
        raise AppLinksProbeFailure("redirect_forbidden")
    if 300 <= status_code < 400:
        raise AppLinksProbeFailure("redirect_forbidden")
    if _is_cloudflare_1033(status_code, live_bytes):
        raise AppLinksProbeFailure("cloudflare_1033_origin_unreachable")
    if status_code != 200:
        raise AppLinksProbeFailure(f"unexpected_http_status_{status_code}")

    content_type = _content_type(headers)
    if content_type != "application/json":
        raise AppLinksProbeFailure("content_type_not_application_json")

    live_payload = _strict_json_array(live_bytes, label="live_assetlinks")
    if live_payload != tracked_payload:
        raise AppLinksProbeFailure("assetlinks_semantic_mismatch")
    if live_bytes != tracked_bytes:
        raise AppLinksProbeFailure("assetlinks_byte_mismatch")

    return AppLinksProbeResult(
        contract_name=CONTRACT_NAME,
        status="pass",
        url=ASSET_LINKS_URL,
        final_url=final_url,
        http_status=status_code,
        content_type=content_type,
        payload_sha256=hashlib.sha256(live_bytes).hexdigest(),
        association_file_matches=True,
        device_verification_evaluated=False,
    )


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        print("usage: probe_android_app_links_postdeploy.py", file=sys.stderr)
        return 2
    try:
        result = probe_android_app_links()
    except AppLinksProbeFailure as exc:
        print(f"Android App Links post-deploy probe failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
