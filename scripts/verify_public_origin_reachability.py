#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / ".codex-studio" / "published" / "PUBLIC_ORIGIN_REACHABILITY_GATE.generated.json"
DEFAULT_BASE_URL = "https://chummer.run/"
USER_AGENT = "ChummerPublicOriginGate/1.0"


@dataclass
class ReachabilityResult:
    status: str
    base_url: str
    final_url: str | None
    http_status: int | None
    cloudflare_ray: str | None
    server: str | None
    detected_error_code: str | None
    failure_reason: str | None
    generated_at: str
    body_excerpt: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail-closed public-origin gate for the live chummer.run surface.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Public URL to open exactly.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Receipt path to write.")
    return parser.parse_args(argv)


def normalize_body_excerpt(body: bytes, limit: int = 600) -> str:
    text = body.decode("utf-8", errors="replace").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def header_lookup(headers: Mapping[str, str], key: str) -> str | None:
    for current_key, value in headers.items():
        if current_key.lower() == key.lower():
            return value
    return None


def detect_failure_reason(http_status: int | None, body_excerpt: str, headers: Mapping[str, str]) -> tuple[str | None, str | None]:
    lowered = body_excerpt.lower()
    if http_status == 530 and "error code: 1033" in lowered:
        return "1033", "cloudflare_tunnel_unresolvable"
    if "cloudflare tunnel error" in lowered and "1033" in lowered:
        return "1033", "cloudflare_tunnel_unresolvable"
    if http_status and http_status >= 400:
        return None, f"http_{http_status}"
    if "<!doctype html>" not in lowered:
        return None, "public_shell_missing_doctype"
    if "chummer" not in lowered:
        return None, "public_shell_missing_brand"
    if header_lookup(headers, "server") and "cloudflare" in (header_lookup(headers, "server") or "").lower():
        return None, None
    return None, None


def fetch_public_origin(url: str) -> tuple[int | None, str | None, dict[str, str], bytes]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            return response.getcode(), response.geturl(), dict(response.headers.items()), response.read()
    except HTTPError as exc:
        return exc.code, exc.geturl(), dict(exc.headers.items()), exc.read()
    except URLError as exc:
        raise RuntimeError(f"url_error:{exc.reason}") from exc


def verify_public_origin(url: str) -> ReachabilityResult:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        http_status, final_url, headers, body = fetch_public_origin(url)
    except Exception as exc:
        return ReachabilityResult(
            status="fail",
            base_url=url,
            final_url=None,
            http_status=None,
            cloudflare_ray=None,
            server=None,
            detected_error_code=None,
            failure_reason=str(exc),
            generated_at=now,
            body_excerpt="",
        )

    body_excerpt = normalize_body_excerpt(body)
    detected_error_code, failure_reason = detect_failure_reason(http_status, body_excerpt, headers)
    status = "pass" if failure_reason is None else "fail"
    return ReachabilityResult(
        status=status,
        base_url=url,
        final_url=final_url,
        http_status=http_status,
        cloudflare_ray=header_lookup(headers, "cf-ray"),
        server=header_lookup(headers, "server"),
        detected_error_code=detected_error_code,
        failure_reason=failure_reason,
        generated_at=now,
        body_excerpt=body_excerpt,
    )


def write_receipt(result: ReachabilityResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = verify_public_origin(args.base_url)
    write_receipt(result, Path(args.output))
    if result.status != "pass":
        print(
            f"public origin gate failed: {result.failure_reason} "
            f"(status={result.http_status}, code={result.detected_error_code}, final_url={result.final_url})",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(asdict(result), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
