#!/usr/bin/env python3
"""Audit or set Cloudflare Browser Cache TTL to respect origin headers."""

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
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener


CONTRACT = "chummer.cloudflare-browser-cache-ttl.v1"
CONFIRMATION = "RESPECT_ORIGIN_BROWSER_CACHE_TTL"
RESPECT_ORIGIN_VALUE = 0
MAX_RESPONSE_BYTES = 1024 * 1024
ZONE_NAME = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")
ZONE_ID = re.compile(r"[0-9a-f]{32}")


class BrowserCacheTtlError(RuntimeError):
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
        raise BrowserCacheTtlError("zone_name_invalid")
    return zone


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
        raise BrowserCacheTtlError("cloudflare_credentials_unavailable")
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
        raise BrowserCacheTtlError("cloudflare_transport_failed") from exc
    with response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        status = int(response.status)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise BrowserCacheTtlError("cloudflare_response_too_large", status)
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrowserCacheTtlError("cloudflare_response_invalid", status) from exc
    if not isinstance(decoded, dict):
        raise BrowserCacheTtlError("cloudflare_response_invalid", status)
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
        "User-Agent": "Chummer-Browser-Cache-TTL/1",
        "X-Auth-Email": email,
        "X-Auth-Key": api_key,
    }
    encoded = (
        None
        if body is None
        else json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    status, payload = transport(
        method,
        f"https://api.cloudflare.com/client/v4{path}",
        headers,
        encoded,
    )
    if status < 200 or status >= 300 or payload.get("success") is not True:
        raise BrowserCacheTtlError("cloudflare_api_rejected", status)
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
        raise BrowserCacheTtlError("cloudflare_zone_not_unique")
    zone = zones[0]
    zone_id = str(zone.get("id") or "").strip().lower()
    if (
        zone.get("name") != zone_name
        or zone.get("status") != "active"
        or ZONE_ID.fullmatch(zone_id) is None
    ):
        raise BrowserCacheTtlError("cloudflare_zone_identity_invalid")
    return zone_id


def read_browser_cache_ttl(
    transport: Transport,
    *,
    zone_id: str,
    email: str,
    api_key: str,
) -> int:
    payload = cloudflare_request(
        transport,
        method="GET",
        path=f"/zones/{zone_id}/settings/browser_cache_ttl",
        email=email,
        api_key=api_key,
    )
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("id") != "browser_cache_ttl":
        raise BrowserCacheTtlError("browser_cache_ttl_result_invalid")
    value = result.get("value")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BrowserCacheTtlError("browser_cache_ttl_value_invalid")
    return value


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
    execute_change: bool,
    confirmation: str,
    expected_current_value: int | None,
    receipt_path: Path | None,
    transport: Transport = urllib_transport,
) -> dict[str, Any]:
    if execute_change and confirmation != CONFIRMATION:
        raise BrowserCacheTtlError("exact_confirmation_required")
    if not execute_change and confirmation:
        raise BrowserCacheTtlError("confirmation_without_execute")
    if execute_change and expected_current_value is None:
        raise BrowserCacheTtlError("expected_current_value_required")
    if expected_current_value is not None and expected_current_value < 0:
        raise BrowserCacheTtlError("expected_current_value_invalid")

    zone = normalize_zone_name(zone_name)
    email, api_key = credentials_from_environment()
    zone_id = resolve_zone_id(
        transport,
        zone_name=zone,
        email=email,
        api_key=api_key,
    )
    before = read_browser_cache_ttl(
        transport,
        zone_id=zone_id,
        email=email,
        api_key=api_key,
    )
    if expected_current_value is not None and before != expected_current_value:
        raise BrowserCacheTtlError("browser_cache_ttl_precondition_failed")

    mutation_issued = execute_change and before != RESPECT_ORIGIN_VALUE
    if mutation_issued:
        cloudflare_request(
            transport,
            method="PATCH",
            path=f"/zones/{zone_id}/settings/browser_cache_ttl",
            email=email,
            api_key=api_key,
            body={"value": RESPECT_ORIGIN_VALUE},
        )
        if receipt_path is not None:
            atomic_write_receipt(
                receipt_path,
                {
                    "contractName": CONTRACT,
                    "generatedAtUtc": utc_now(),
                    "status": "mutation_accepted_verification_pending",
                    "mode": "execute",
                    "zoneName": zone,
                    "zoneId": zone_id,
                    "settingId": "browser_cache_ttl",
                    "beforeValueSeconds": before,
                    "afterValueSeconds": None,
                    "desiredValueSeconds": RESPECT_ORIGIN_VALUE,
                    "desiredMode": "respect_existing_headers",
                    "expectedCurrentValueSeconds": expected_current_value,
                    "preconditionMatched": True,
                    "postconditionMatched": False,
                    "mutationIssued": True,
                    "verificationComplete": False,
                    "doNotRetryMutation": True,
                    "secretsExposed": False,
                },
            )
    after = (
        read_browser_cache_ttl(
            transport,
            zone_id=zone_id,
            email=email,
            api_key=api_key,
        )
        if execute_change
        else before
    )
    if execute_change and after != RESPECT_ORIGIN_VALUE:
        raise BrowserCacheTtlError("browser_cache_ttl_postcondition_failed")

    receipt = {
        "contractName": CONTRACT,
        "generatedAtUtc": utc_now(),
        "status": (
            "audit_passed"
            if not execute_change
            else "updated"
            if mutation_issued
            else "already_compliant"
        ),
        "mode": "execute" if execute_change else "audit",
        "zoneName": zone,
        "zoneId": zone_id,
        "settingId": "browser_cache_ttl",
        "beforeValueSeconds": before,
        "afterValueSeconds": after,
        "desiredValueSeconds": RESPECT_ORIGIN_VALUE,
        "desiredMode": "respect_existing_headers",
        "expectedCurrentValueSeconds": expected_current_value,
        "preconditionMatched": expected_current_value is None or before == expected_current_value,
        "postconditionMatched": after == RESPECT_ORIGIN_VALUE,
        "mutationIssued": mutation_issued,
        "verificationComplete": True,
        "doNotRetryMutation": False,
        "secretsExposed": False,
    }
    if receipt_path is not None:
        atomic_write_receipt(receipt_path, receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zone-name", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--expected-current-value", type=int)
    parser.add_argument("--receipt", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = execute(
            zone_name=args.zone_name,
            execute_change=args.execute,
            confirmation=args.confirm,
            expected_current_value=args.expected_current_value,
            receipt_path=args.receipt,
        )
    except BrowserCacheTtlError as exc:
        print(
            json.dumps(
                {
                    "contractName": CONTRACT,
                    "status": "failed",
                    "failureCode": exc.code,
                    "httpStatus": exc.http_status,
                    "mutationState": "not_confirmed",
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
                    "mutationState": "not_confirmed",
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
