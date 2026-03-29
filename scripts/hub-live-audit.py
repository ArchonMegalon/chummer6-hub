#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener


BANNED_COPY = re.compile(r"\b(Read the linked detail|Read more|Learn more)\b", re.IGNORECASE)


@dataclass
class AuditRoute:
    path: str
    expected_text: str | None = None
    required_texts: tuple[str, ...] = ()
    forbidden_texts: tuple[str, ...] = ()
    expected_status: int = 200
    expects_header_count: int | None = None
    allows_redirect: bool = False


class HeaderCounter(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "header":
            return
        attrs_map = dict(attrs)
        if "data-site-header" in attrs_map:
            self.count += 1


class NoRedirectHandler(HTTPRedirectHandler):
    def http_error_301(self, req, fp, code, msg, headers):  # pragma: no cover - exercised via operational probes
        return fp

    def http_error_302(self, req, fp, code, msg, headers):  # pragma: no cover - exercised via operational probes
        return fp

    def http_error_303(self, req, fp, code, msg, headers):  # pragma: no cover - exercised via operational probes
        return fp

    def http_error_307(self, req, fp, code, msg, headers):  # pragma: no cover - exercised via operational probes
        return fp

    def http_error_308(self, req, fp, code, msg, headers):  # pragma: no cover - exercised via operational probes
        return fp


def fetch(
    base_url: str,
    path: str,
    *,
    public_host: str | None = None,
    forwarded_proto: str | None = None,
    follow_redirects: bool = True,
    method: str = "GET",
    body: bytes | None = None,
    request_headers: dict[str, str] | None = None,
) -> tuple[int, str, dict[str, str], str]:
    url = urljoin(base_url, path)
    headers = {"User-Agent": "chummer-hub-live-audit"}
    if public_host:
        headers["Host"] = public_host
    if forwarded_proto:
        headers["X-Forwarded-Proto"] = forwarded_proto
    if request_headers:
        headers.update(request_headers)

    request = Request(url, headers=headers, data=body, method=method)
    opener = build_opener() if follow_redirects else build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=20) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            final_url = response.geturl()
            return status, body, response_headers, final_url
    except HTTPError as exc:  # pragma: no cover - exercised via operational probes
        body = exc.read().decode("utf-8", errors="replace")
        response_headers = {key.lower(): value for key, value in exc.headers.items()}
        return exc.code, body, response_headers, exc.geturl()


def verify_https_redirect(base_url: str, path: str, public_host: str) -> None:
    status, _, headers, _ = fetch(base_url, path, public_host=public_host, follow_redirects=False)
    if status not in {301, 302, 307, 308}:
        raise AssertionError(f"{path} returned {status}, expected an HTTPS redirect")

    location = headers.get("location")
    expected_location = f"https://{public_host}{path}"
    if location != expected_location:
        raise AssertionError(f"{path} redirected to {location!r}, expected {expected_location!r}")

    print(f"ok {path} redirects -> {location}")


def require_snippet(body: str, snippet: str, path: str) -> None:
    if snippet not in body:
        raise AssertionError(f"{path} missing required text: {snippet}")


def extract_antiforgery_token(body: str, path: str) -> str:
    match = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', body)
    if not match:
        raise AssertionError(f"{path} missing antiforgery token")

    return unescape(match.group(1))


def extract_cookie(headers: dict[str, str], *, path: str) -> str:
    cookie = headers.get("set-cookie")
    if not cookie:
        raise AssertionError(f"{path} did not return a cookie")

    return cookie.split(";", 1)[0]


def verify_signed_in_work_audit(
    base_url: str,
    *,
    email: str,
    public_host: str | None = None,
    forwarded_proto: str | None = None,
) -> None:
    status, body, headers, _ = fetch(
        base_url,
        "/login?next=%2Faccount%2Fwork",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
    )
    if status != 200:
        raise AssertionError(f"/login returned {status}, expected 200")

    antiforgery_cookie = extract_cookie(headers, path="/login")
    antiforgery_token = extract_antiforgery_token(body, "/login")
    login_form = urlencode(
        {
            "__RequestVerificationToken": antiforgery_token,
            "email": email,
            "next": "/account/work",
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/auth/email/start",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=login_form,
        request_headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": antiforgery_cookie,
        },
    )
    if status != 200:
        raise AssertionError(f"/auth/email/start returned {status}, expected 200")

    callback_match = re.search(r'href="([^"]*/auth/email/callback\?[^"]+)"', body)
    if not callback_match:
        raise AssertionError("/auth/email/start did not render the preview callback link")

    status, _, headers, _ = fetch(
        base_url,
        unescape(callback_match.group(1)),
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        follow_redirects=False,
        request_headers={"Cookie": antiforgery_cookie},
    )
    if status not in {301, 302, 303, 307, 308}:
        raise AssertionError(f"/auth/email/callback returned {status}, expected redirect")

    auth_cookie = extract_cookie(headers, path="/auth/email/callback")
    cookie_header = f"{antiforgery_cookie}; {auth_cookie}"
    location = headers.get("location", "")
    if not location.endswith("/account/work"):
        raise AssertionError(f"/auth/email/callback redirected to {location!r}, expected /account/work")

    status, body, _, _ = fetch(
        base_url,
        "/api/v1/campaign-spine/me",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/api/v1/campaign-spine/me returned {status}, expected 200")

    summary = json.loads(body)
    workspaces = summary.get("workspaces") or []
    if not workspaces:
        raise AssertionError("signed-in campaign summary did not expose any workspaces")

    status, body, _, _ = fetch(
        base_url,
        "/account/access",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/account/access returned {status}, expected 200")
    require_snippet(body, "Cross-device recovery", "/account/access")
    require_snippet(body, "What stays on this device", "/account/access")

    workspace_id = workspaces[0]["workspaceId"]
    workspace_path = f"/account/work/workspaces/{workspace_id}"
    status, body, _, _ = fetch(
        base_url,
        workspace_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_path} returned {status}, expected 200")

    for snippet in (
        "What changed for me",
        "Move governed roster state",
        "Transfer governed roster state",
        "Launch governed prep packet",
        "GM prep library and travel mode",
    ):
        require_snippet(body, snippet, workspace_path)

    search_path = f"{workspace_path}?prepQuery=opposition"
    status, search_body, _, _ = fetch(
        base_url,
        search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{search_path} returned {status}, expected 200")
    require_snippet(search_body, "Search results:", search_path)
    require_snippet(search_body, "opposition", search_path)

    workspace_token = extract_antiforgery_token(body, workspace_path)
    plan_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/roster-transfer-plan"
    status, body, _, _ = fetch(
        base_url,
        plan_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{plan_path} returned {status}, expected 200")

    roster_plan = json.loads(body)
    dossier_options = roster_plan.get("dossierOptions") or []
    target_groups = roster_plan.get("targetGroups") or []
    if not dossier_options:
        raise AssertionError(f"{plan_path} did not expose dossier options")
    if not target_groups:
        raise AssertionError(f"{plan_path} did not expose target groups")

    prep_library_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=opposition"
    status, body, _, _ = fetch(
        base_url,
        prep_library_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_path} returned {status}, expected 200")

    prep_library = json.loads(body)
    prep_items = prep_library.get("items") or []
    if not prep_items:
        raise AssertionError("prep-library search did not expose any governed packet to launch")

    runs = workspaces[0].get("runs") or []
    target_run = runs[0] if runs else {}
    prep_launch_body = json.dumps(
        {
            "packetId": prep_items[0]["packetId"],
            "targetRunId": target_run.get("runId"),
            "targetSceneId": target_run.get("activeSceneId"),
            "note": "Signed-in live audit binding governed opposition truth.",
        }
    ).encode("utf-8")
    launch_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library/launches"
    status, body, _, _ = fetch(
        base_url,
        launch_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=prep_launch_body,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"{launch_path} returned {status}: {body[:400]}")

    prep_launch = json.loads(body)
    if not prep_launch.get("launchId"):
        raise AssertionError("prep launch response did not expose a launch id")

    payload = json.dumps(
        {
            "dossierId": dossier_options[0]["dossierId"],
            "targetGroupId": target_groups[0]["groupId"],
            "targetCampaignTitle": target_groups[0].get("suggestedCampaignTitle"),
            "note": "Live signed-in roster transfer audit.",
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/campaign-spine/me/roster-transfers",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=payload,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"/api/v1/campaign-spine/me/roster-transfers returned {status}: {body[:400]}")

    transfer = json.loads(body)
    status, body, _, final_url = fetch(
        base_url,
        "/account/work",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/account/work returned {status}, expected 200")

    require_snippet(body, "Recent governed roster moves", "/account/work")
    require_snippet(body, transfer["runnerHandle"], "/account/work")
    require_snippet(body, "GM prep launch", "/account/work")
    status, body, _, _ = fetch(
        base_url,
        workspace_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_path} returned {status}, expected 200 after prep launch")
    require_snippet(body, "Recent governed prep launches", workspace_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_path)
    print(
        "ok signed-in /account/work -> "
        f"{final_url} workspace={workspace_id} prep_launch={prep_launch['launchId']} transfer={transfer['transferId']} runner={transfer['runnerHandle']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the public Chummer Hub surface.")
    parser.add_argument("--base-url", default="https://chummer.run", help="Base URL to audit.")
    parser.add_argument("--public-host", default=None, help="Optional Host header for reverse-proxied local edge checks.")
    parser.add_argument("--forwarded-proto", default=None, help="Optional X-Forwarded-Proto header for reverse-proxied local edge checks.")
    parser.add_argument("--verify-http-redirects", action="store_true", help="Verify that the local HTTP edge redirects to the public HTTPS host.")
    parser.add_argument("--verify-signed-in-work", action="store_true", help="Verify the signed-in account/work journey, including the governed roster-transfer live action.")
    parser.add_argument("--signed-in-email", default=None, help="Optional example.invalid email used for the signed-in work audit. Defaults to a generated value.")
    parser.add_argument("--poll-seconds", type=int, default=0, help="Sleep before starting the audit.")
    args = parser.parse_args()

    if args.poll_seconds > 0:
        time.sleep(args.poll_seconds)

    if args.verify_http_redirects and not args.public_host:
        raise AssertionError("--verify-http-redirects requires --public-host")

    routes = [
        AuditRoute("/", "Create account to get preview", required_texts=("Final pool 9",), expects_header_count=1),
        AuditRoute("/what-is-chummer", "One product for rules truth, living dossiers, and session return.", expects_header_count=1),
        AuditRoute(
            "/now",
            "Current preview, visible proof, and known posture",
            required_texts=("What you can verify now", "Build, explain, and run with visible evidence", "Status guide"),
            expects_header_count=1),
        AuditRoute(
            "/downloads",
            "Install the current preview",
            required_texts=("Create account to get preview", "Already have an account? Sign in", "Advanced download options", "Release notes, known issues, and requirements"),
            forbidden_texts=("Package details",),
            expects_header_count=1),
        AuditRoute("/horizons", "What Chummer is building toward", required_texts=("Preparing next", "Designing in public", "Research track", "Status guide"), forbidden_texts=("Research tracks",), expects_header_count=1),
        AuditRoute("/artifacts", "Current proof surfaces", required_texts=("Preview in progress", "Status guide", "Anyone evaluating the preview"), expects_header_count=1),
        AuditRoute("/artifacts/current-preview-build", "Current preview build", required_texts=("Anyone evaluating the preview",), forbidden_texts=(">public<",), expects_header_count=1),
        AuditRoute("/roadmap/nexus-pan", "NEXUS-PAN", required_texts=("Anyone evaluating the preview",), forbidden_texts=(">public<",), expects_header_count=1),
        AuditRoute("/participate", "Choose how to participate", expects_header_count=1),
        AuditRoute("/help", "Get help without guessing", required_texts=("Fallback:", "Support, survey, and assistant data stay on a bounded clock"), expects_header_count=1),
        AuditRoute("/faq", "Plain answers before you spend more time", expects_header_count=1),
        AuditRoute("/contact", "Open the right support case", expects_header_count=1),
        AuditRoute("/privacy", "What Chummer stores, and what it does not", required_texts=("Support, survey, and assistant data stay on a bounded clock",), expects_header_count=1),
        AuditRoute("/terms", "Preview terms in plain language", expects_header_count=1),
        AuditRoute("/robots.txt", "Disallow: /"),
    ]

    if args.verify_http_redirects:
        for redirect_path in ("/", "/downloads", "/contact"):
            verify_https_redirect(args.base_url, redirect_path, args.public_host)

    for route in routes:
        status, body, headers, final_url = fetch(
            args.base_url,
            route.path,
            public_host=args.public_host,
            forwarded_proto=args.forwarded_proto,
        )
        if status != route.expected_status:
            raise AssertionError(f"{route.path} returned {status}, expected {route.expected_status}")
        if route.expected_text and route.expected_text not in body:
            raise AssertionError(f"{route.path} missing expected text: {route.expected_text}")
        for snippet in route.required_texts:
            if snippet not in body:
                raise AssertionError(f"{route.path} missing required text: {snippet}")
        for snippet in route.forbidden_texts:
            if snippet in body:
                raise AssertionError(f"{route.path} rendered forbidden text: {snippet}")
        if route.path != "/robots.txt":
            robots = headers.get("x-robots-tag", "")
            if "noindex" not in robots.lower():
                raise AssertionError(f"{route.path} missing X-Robots-Tag noindex header")
            if BANNED_COPY.search(body):
                raise AssertionError(f"{route.path} rendered banned generic CTA copy")
            if route.path == "/" and body.count("Final pool 9") != 1:
                raise AssertionError("/ rendered the proof teaser more than once")
            if route.expects_header_count is not None:
                parser_ = HeaderCounter()
                parser_.feed(body)
                if parser_.count != route.expects_header_count:
                    raise AssertionError(f"{route.path} rendered {parser_.count} site headers, expected {route.expects_header_count}")
        print(f"ok {route.path} -> {final_url}")

    status, _, _, final_url = fetch(
        args.base_url,
        "/status",
        public_host=args.public_host,
        forwarded_proto=args.forwarded_proto,
    )
    if status != 200 or not final_url.rstrip("/").endswith("/now"):
        raise AssertionError("/status did not resolve to /now")
    print(f"ok /status -> {final_url}")

    status, body, _, final_url = fetch(
        args.base_url,
        "/api/public/weekly-pulse",
        public_host=args.public_host,
        forwarded_proto=args.forwarded_proto,
    )
    if status != 200 or '"contract_name": "chummer.weekly_product_pulse"' not in body:
        raise AssertionError("/api/public/weekly-pulse did not serve the mirrored weekly pulse artifact")
    print(f"ok /api/public/weekly-pulse -> {final_url}")

    status, body, _, final_url = fetch(
        args.base_url,
        "/api/public/privacy-boundaries",
        public_host=args.public_host,
        forwarded_proto=args.forwarded_proto,
    )
    if status != 200 or '"contractName": "chummer.public_privacy_boundaries"' not in body:
        raise AssertionError("/api/public/privacy-boundaries did not serve the mirrored privacy-boundary artifact")
    print(f"ok /api/public/privacy-boundaries -> {final_url}")

    if args.verify_signed_in_work:
        signed_in_email = args.signed_in_email or f"live-audit-{int(time.time())}@example.invalid"
        verify_signed_in_work_audit(
            args.base_url,
            email=signed_in_email,
            public_host=args.public_host,
            forwarded_proto=args.forwarded_proto,
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - operational script
        print(f"hub live audit failed: {exc}", file=sys.stderr)
        raise
