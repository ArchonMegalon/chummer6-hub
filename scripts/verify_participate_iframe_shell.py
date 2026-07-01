#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
REMOVED_SUMMARY = "Public requests, clear bugs, useful ideas."
REMOVED_BOARD_EYEBROW = '<p class="eyebrow">Board</p>'


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def strip_iframe_tags(html: str) -> str:
    return re.sub(r"<iframe\b[\s\S]*?(?:</iframe>|>)", " ", html, flags=re.IGNORECASE)


def iframe_src_values(html: str) -> list[str]:
    return re.findall(r"<iframe\b[^>]*\bsrc=\"([^\"]+)\"", html, flags=re.IGNORECASE)


def build_participate_segment(controller_source: str) -> str:
    start = controller_source.index("BuildFirstPartyParticipateBoardAsync")
    end_marker = (
        "TryRenderFirstPartyParticipatePostDetailAsync"
        if "TryRenderFirstPartyParticipatePostDetailAsync" in controller_source
        else "private bool ShouldShortCircuitHostedBoardUpstream"
    )
    end = controller_source.index(end_marker)
    return controller_source[start:end]


def verify_source() -> dict[str, Any]:
    public_controller = read_text("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    legacy_controller = read_text("Chummer.Run.Api/Controllers/ParticipateController.cs")
    view = read_text("Chummer.Run.Api/Views/PublicLanding/Partizipate.cshtml")
    public_segment = build_participate_segment(public_controller)
    legacy_segment = build_participate_segment(legacy_controller)

    required = {
        "view_has_real_iframe": "<iframe" in view and "data-chummer-participate-frame" in view,
        "view_has_offline_fallback": "participate-board-fallback" in view and "Board offline right now" in view,
        "view_uses_existing_embed_href": 'src="@Model.EmbeddedBoardHref"' in view,
        "view_allows_full_provider_feature_set": 'allow="clipboard-write; fullscreen"' in view and "sandbox" not in view,
        "view_uses_cross_origin_referrer_policy": 'referrerpolicy="strict-origin-when-cross-origin"' in view,
        "view_has_screen_reader_title": '<h1 id="partizipate-title" class="sr-only">Participate</h1>' in view,
        "view_removes_visible_header": "participate-hosted__header" not in view,
        "view_removes_board_eyebrow": REMOVED_BOARD_EYEBROW not in view,
        "view_removes_old_summary": REMOVED_SUMMARY not in view,
        "public_builder_uses_hosted_upstream_iframe": "BuildParticipateFrameHref(hostedBoardUpstream, normalizedBoardPath)" in public_segment,
        "legacy_builder_uses_hosted_upstream_iframe": "BuildParticipateFrameHref(hostedBoardUpstream, normalizedBoardPath)" in legacy_segment,
        "public_builder_summary_is_minimal": 'Summary: "Participate"' in public_segment and REMOVED_SUMMARY not in public_segment,
        "legacy_builder_summary_is_minimal": 'Summary: "Participate"' in legacy_segment and REMOVED_SUMMARY not in legacy_segment,
    }
    failures = [name for name, ok in required.items() if not ok]
    return {
        "status": "pass" if not failures else "fail",
        "required": required,
        "failures": failures,
    }


def fetch(base_url: str, path: str, timeout_seconds: float) -> tuple[int, dict[str, str], str, str]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = Request(url, headers={"User-Agent": "ChummerParticipateIframeShellProof/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, headers, body, response.geturl()
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        headers = {key.lower(): value for key, value in error.headers.items()}
        return error.code, headers, body, error.geturl()
    except URLError as error:
        raise RuntimeError(f"{url}: {error}") from error


def verify_live_route(base_url: str, path: str, timeout_seconds: float) -> dict[str, Any]:
    status_code, headers, body, final_url = fetch(base_url, path, timeout_seconds)
    failures: list[str] = []
    final_path = urlparse(final_url).path
    has_iframe = "data-chummer-participate-frame" in body and "<iframe" in body
    has_fallback = "participate-board-fallback" in body and "Board offline right now" in body
    iframe_srcs = iframe_src_values(body)
    body_without_iframes = strip_iframe_tags(body)
    iframe_uses_productlift = any("productlift.dev" in source.lower() for source in iframe_srcs)
    iframe_uses_old_proxy = any("/participate/board" in source and "embed=1" in source for source in iframe_srcs)

    require(status_code == 200, failures, f"{path} expected 200, got {status_code}")
    require(final_path == "/participate", failures, f"{path} final path expected /participate, got {final_path}")
    require("Participate" in body, failures, f"{path} missing Participate title")
    require(has_iframe or has_fallback, failures, f"{path} missing iframe or offline fallback")
    if has_iframe:
        require(iframe_uses_productlift, failures, f"{path} iframe does not point at ProductLift")
        require(not iframe_uses_old_proxy, failures, f"{path} iframe still points at the same-origin board proxy")
    require(REMOVED_SUMMARY not in body, failures, f"{path} still renders removed summary")
    require(REMOVED_BOARD_EYEBROW not in body, failures, f"{path} still renders Board eyebrow")
    require("participate-hosted__header" not in body, failures, f"{path} still renders participate-hosted header")
    require("ProductLift" not in body_without_iframes, failures, f"{path} leaks provider brand outside the iframe")
    require("productlift.dev" not in body_without_iframes.lower(), failures, f"{path} leaks provider domain outside the iframe")

    return {
        "status": "pass" if not failures else "fail",
        "route": path,
        "status_code": status_code,
        "final_url": final_url,
        "final_path": final_path,
        "content_type": headers.get("content-type", ""),
        "has_iframe": has_iframe,
        "iframe_srcs": iframe_srcs,
        "has_offline_fallback": has_fallback,
        "iframe_uses_productlift": iframe_uses_productlift,
        "iframe_uses_old_proxy": iframe_uses_old_proxy,
        "removed_summary_present": REMOVED_SUMMARY in body,
        "removed_board_eyebrow_present": REMOVED_BOARD_EYEBROW in body,
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "failures": failures,
    }


def verify(base_url: str | None, timeout_seconds: float) -> dict[str, Any]:
    source = verify_source()
    live_routes: list[dict[str, Any]] = []
    failures = list(source.get("failures", []))
    if base_url:
        for route in ("/participate", "/partizipate"):
            live = verify_live_route(base_url, route, timeout_seconds)
            live_routes.append(live)
            if live.get("status") != "pass":
                failures.extend(live.get("failures", []))

    return {
        "contractName": "chummer.participate_iframe_shell.v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass" if not failures else "fail",
        "base_url": base_url.rstrip("/") if base_url else "",
        "source": source,
        "live": live_routes,
        "route_count": len(live_routes),
        "iframe_route_count": sum(1 for route in live_routes if route.get("has_iframe")),
        "offline_fallback_route_count": sum(1 for route in live_routes if route.get("has_offline_fallback")),
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Participate renders only the existing iframe shell or offline fallback.")
    parser.add_argument("--base-url", help="Base URL to verify live Participate shell behavior.")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    result = verify(args.base_url, args.timeout_seconds)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
