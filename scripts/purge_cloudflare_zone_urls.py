#!/usr/bin/env python3
"""Audit or purge an exact bounded set of same-zone Cloudflare cache URLs."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener


CONTRACT = "chummer.cloudflare-exact-url-cache-purge/v1"
CONFIRMATION = "PURGE_EXACT_CLOUDFLARE_URLS"
MAX_URLS = 30
MAX_RESPONSE_BYTES = 1024 * 1024
ZONE_NAME = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")
ZONE_ID = re.compile(r"[0-9a-f]{32}")


class PurgeError(RuntimeError):
    def __init__(self, code: str, http_status: int | None = None) -> None:
        self.code = code if re.fullmatch(r"[a-z0-9_]{3,96}", code) else "unsafe_error"
        self.http_status = http_status
        super().__init__(self.code)


Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, dict[str, Any]]]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_zone_name(value: str) -> str:
    zone = value.strip().lower().rstrip(".")
    if not zone or ZONE_NAME.fullmatch(zone) is None or ".." in zone or "." not in zone:
        raise PurgeError("zone_name_invalid")
    return zone


def normalize_urls(values: list[str], zone_name: str) -> list[str]:
    if not values or len(values) > MAX_URLS:
        raise PurgeError("url_count_invalid")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        parsed = urlsplit(value.strip())
        try:
            port = parsed.port
        except ValueError as exc:
            raise PurgeError("purge_url_invalid") from exc
        if (
            parsed.scheme.lower() != "https"
            or parsed.hostname != zone_name
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
            or not parsed.path.startswith("/")
            or parsed.path.startswith("//")
            or parsed.query
            or parsed.fragment
        ):
            raise PurgeError("purge_url_invalid")
        canonical = f"https://{zone_name}{parsed.path}"
        if canonical in seen:
            raise PurgeError("purge_url_duplicate")
        seen.add(canonical)
        normalized.append(canonical)
    return normalized


def credentials_from_environment() -> tuple[str, str]:
    email = os.environ.get("CLOUDFLARE_EMAIL", "").strip()
    api_key = os.environ.get("CLOUDFLARE_GLOBAL_API_KEY", "").strip()
    if (
        not email
        or len(email) > 320
        or "@" not in email
        or not api_key
        or len(api_key) > 1024
        or "\n" in email
        or "\r" in email
        or "\n" in api_key
        or "\r" in api_key
    ):
        raise PurgeError("cloudflare_credentials_unavailable")
    return email, api_key


def urllib_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
) -> tuple[int, dict[str, Any]]:
    opener = build_opener(ProxyHandler({}))
    request = Request(url, data=body, headers=headers, method=method)
    try:
        response = opener.open(request, timeout=30)
    except HTTPError as exc:
        response = exc
    except (URLError, TimeoutError) as exc:
        raise PurgeError("cloudflare_transport_failed") from exc
    with response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        status = int(response.status)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise PurgeError("cloudflare_response_too_large", status)
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PurgeError("cloudflare_response_invalid", status) from exc
    if not isinstance(decoded, dict):
        raise PurgeError("cloudflare_response_invalid", status)
    return status, decoded


def cloudflare_request(
    transport: Transport,
    *,
    method: str,
    path: str,
    email: str,
    api_key: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Chummer-Exact-Cache-Purge/1",
        "X-Auth-Email": email,
        "X-Auth-Key": api_key,
    }
    encoded = None if body is None else json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    status, payload = transport(method, f"https://api.cloudflare.com/client/v4{path}", headers, encoded)
    if status < 200 or status >= 300 or payload.get("success") is not True:
        raise PurgeError("cloudflare_api_rejected", status)
    return payload


def resolve_zone_id(
    transport: Transport,
    *,
    zone_name: str,
    email: str,
    api_key: str,
) -> str:
    query = urlencode({"name": zone_name, "status": "active", "per_page": "2"})
    payload = cloudflare_request(
        transport,
        method="GET",
        path=f"/zones?{query}",
        email=email,
        api_key=api_key,
    )
    zones = payload.get("result")
    if not isinstance(zones, list) or len(zones) != 1 or not isinstance(zones[0], dict):
        raise PurgeError("cloudflare_zone_not_unique")
    zone = zones[0]
    zone_id = str(zone.get("id") or "").strip().lower()
    if zone.get("name") != zone_name or zone.get("status") != "active" or ZONE_ID.fullmatch(zone_id) is None:
        raise PurgeError("cloudflare_zone_identity_invalid")
    return zone_id


def atomic_write_receipt(path: Path, payload: dict[str, Any]) -> None:
    target = path.absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def execute(
    *,
    zone_name: str,
    urls: list[str],
    execute_purge: bool,
    confirmation: str,
    receipt_path: Path | None,
    transport: Transport = urllib_transport,
) -> dict[str, Any]:
    if execute_purge and confirmation != CONFIRMATION:
        raise PurgeError("exact_confirmation_required")
    if not execute_purge and confirmation:
        raise PurgeError("confirmation_without_execute")
    zone = normalize_zone_name(zone_name)
    exact_urls = normalize_urls(urls, zone)
    email, api_key = credentials_from_environment()
    zone_id = resolve_zone_id(
        transport,
        zone_name=zone,
        email=email,
        api_key=api_key,
    )
    status = "audit_passed"
    if execute_purge:
        cloudflare_request(
            transport,
            method="POST",
            path=f"/zones/{zone_id}/purge_cache",
            email=email,
            api_key=api_key,
            body={"files": exact_urls},
        )
        status = "purged"
    receipt = {
        "contractName": CONTRACT,
        "generatedAtUtc": utc_now(),
        "status": status,
        "mode": "execute" if execute_purge else "audit",
        "zoneName": zone,
        "zoneId": zone_id,
        "urlCount": len(exact_urls),
        "urls": exact_urls,
        "purgeIssued": execute_purge,
        "secretsExposed": False,
    }
    if receipt_path is not None:
        atomic_write_receipt(receipt_path, receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zone-name", required=True)
    parser.add_argument("--url", action="append", default=[], dest="urls")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--receipt", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = execute(
            zone_name=args.zone_name,
            urls=args.urls,
            execute_purge=args.execute,
            confirmation=args.confirm,
            receipt_path=args.receipt,
        )
    except PurgeError as exc:
        print(
            json.dumps(
                {
                    "contractName": CONTRACT,
                    "status": "failed",
                    "failureCode": exc.code,
                    "httpStatus": exc.http_status,
                    "secretsExposed": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            failure_code = "operator_interrupt"
        elif isinstance(exc, SystemExit):
            raise
        else:
            failure_code = "unexpected_local_failure"
        print(
            json.dumps(
                {
                    "contractName": CONTRACT,
                    "status": "failed",
                    "failureCode": failure_code,
                    "httpStatus": None,
                    "secretsExposed": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 130 if isinstance(exc, KeyboardInterrupt) else 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
