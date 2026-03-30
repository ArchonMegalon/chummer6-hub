#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener


BANNED_COPY = re.compile(r"\b(Read the linked detail|Read more|Learn more)\b", re.IGNORECASE)
SUPPORT_AUDIT_TITLE = "Live audit support verification case"
SUPPORT_AUDIT_SUMMARY = "Signed-in live audit is verifying the assistant-led fix verification lane."
SUPPORT_AUDIT_DETAIL_PREFIX = "Signed-in live audit is verifying the assistant-led fix verification lane on the rebuilt local edge."


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
    max_retries: int = 6,
    retry_delay_seconds: float = 1.0,
) -> tuple[int, str, dict[str, str], str]:
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds cannot be negative")

    attempt = 0
    while True:
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
                body_text = response.read().decode("utf-8", errors="replace")
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                final_url = response.geturl()
        except TimeoutError:
            if attempt >= max_retries:
                raise

            attempt += 1
            delay_seconds = retry_delay_seconds * (2 ** (attempt - 1))
            print(f"timed out on {path}; retrying in {delay_seconds:.1f}s ({attempt}/{max_retries})")
            time.sleep(delay_seconds)
            continue
        except HTTPError as exc:  # pragma: no cover - exercised via operational probes
            status = exc.code
            body_text = exc.read().decode("utf-8", errors="replace")
            response_headers = {key.lower(): value for key, value in exc.headers.items()}
            final_url = exc.geturl()

        if status != 429 or attempt >= max_retries:
            return status, body_text, response_headers, final_url

        attempt += 1
        retry_after = response_headers.get("retry-after")
        if retry_after:
            try:
                delay_seconds = float(retry_after)
            except ValueError:
                delay_seconds = retry_delay_seconds * (2 ** (attempt - 1))
        else:
            delay_seconds = retry_delay_seconds * (2 ** (attempt - 1))
        print(f"rate-limited on {path}; retrying in {delay_seconds:.1f}s ({attempt}/{max_retries})")
        time.sleep(delay_seconds)


def load_json_object(body: str, path: str) -> dict[str, object]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{path} returned invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise AssertionError(f"{path} returned {type(payload).__name__}, expected a JSON object")

    return payload


def resolve_internal_token(explicit_token: str | None, compose_file: str | None) -> str:
    if explicit_token and explicit_token.strip():
        return explicit_token.strip()

    env_token = os.environ.get("FLEET_INTERNAL_API_TOKEN", "").strip()
    if env_token:
        return env_token

    if not compose_file:
        raise AssertionError("signed-in support verification requires an internal automation token")

    compose_ps = subprocess.run(
        ["docker", "compose", "-f", compose_file, "ps", "-q", "chummer-portal"],
        check=False,
        capture_output=True,
        text=True,
    )
    if compose_ps.returncode != 0:
        raise AssertionError(f"could not resolve chummer-portal container from {compose_file}: {compose_ps.stderr.strip()}")

    container_id = next((line.strip() for line in compose_ps.stdout.splitlines() if line.strip()), "")
    if not container_id:
        raise AssertionError(f"could not resolve chummer-portal container from {compose_file}")

    inspect = subprocess.run(
        ["docker", "inspect", "--format", "{{range .Config.Env}}{{println .}}{{end}}", container_id],
        check=False,
        capture_output=True,
        text=True,
    )
    if inspect.returncode != 0:
        raise AssertionError(f"could not inspect {container_id} for FLEET_INTERNAL_API_TOKEN: {inspect.stderr.strip()}")

    token_prefix = "FLEET_INTERNAL_API_TOKEN="
    for line in inspect.stdout.splitlines():
        if line.startswith(token_prefix):
            token = line[len(token_prefix):].strip()
            if token:
                return token

    raise AssertionError("signed-in support verification requires FLEET_INTERNAL_API_TOKEN, but it is not configured on chummer-portal")


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


def extract_first_match(body: str, pattern: str, path: str, label: str) -> str:
    match = re.search(pattern, body, re.IGNORECASE)
    if not match:
        raise AssertionError(f"{path} missing {label}")

    return unescape(match.group(1)).strip()


def extract_optional_match(body: str, pattern: str) -> str | None:
    match = re.search(pattern, body, re.IGNORECASE)
    if not match:
        return None

    return unescape(match.group(1)).strip()


def split_fragment_path(path: str) -> tuple[str, str | None]:
    if "#" not in path:
        return path, None

    base_path, fragment = path.split("#", 1)
    return base_path, fragment or None


def fetch_fragment_target(
    base_url: str,
    path: str,
    *,
    public_host: str | None,
    forwarded_proto: str | None,
    cookie_header: str,
    required_texts: tuple[str, ...],
) -> str:
    base_path, fragment = split_fragment_path(path)
    status, body, _, _ = fetch(
        base_url,
        base_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{path} returned {status}, expected 200")

    if fragment:
        require_snippet(body, f'id="{fragment}"', path)

    for snippet in required_texts:
        require_snippet(body, snippet, path)

    return body


def extract_antiforgery_token(body: str, path: str) -> str:
    match = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', body)
    if not match:
        raise AssertionError(f"{path} missing antiforgery token")

    return unescape(match.group(1))


def extract_dispatch_path(body: str, path: str) -> str:
    return extract_first_match(body, r'href="([^"]*/downloads/install/[^"]+)"', path, "signed-in install handoff link")


def extract_claim_code(body: str, path: str) -> str:
    return extract_first_match(body, r'id="claimCodeValue"[^>]*>([^<]+)<', path, "install claim code")


def extract_subject_id(body: str, path: str) -> str:
    return extract_first_match(body, r'const subjectId = "([^"]+)"', path, "signed-in subject id")


def extract_cookie(headers: dict[str, str], *, path: str) -> str:
    cookie = headers.get("set-cookie")
    if not cookie:
        raise AssertionError(f"{path} did not return a cookie")

    return cookie.split(";", 1)[0]


def ensure_claimed_device(
    base_url: str,
    *,
    cookie_header: str,
    public_host: str | None = None,
    forwarded_proto: str | None = None,
) -> tuple[dict[str, object], str, str]:
    status, body, _, _ = fetch(
        base_url,
        "/downloads",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/downloads returned {status}, expected 200 for install handoff discovery")

    dispatch_path = extract_dispatch_path(body, "/downloads")
    status, body, _, _ = fetch(
        base_url,
        dispatch_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{dispatch_path} returned {status}, expected 200")

    claim_code = extract_claim_code(body, dispatch_path)
    installation_id = f"install-live-audit-{time.time_ns()}"
    initial_version = "0.0-live-audit"
    redeem_body = json.dumps(
        {
            "claimCode": claim_code,
            "installationId": installation_id,
            "headId": "avalonia",
            "applicationVersion": initial_version,
            "channelId": "preview",
            "platform": "linux",
            "arch": "x64",
            "publicKey": "live-audit-public-key",
            "hostLabel": "live-audit-host",
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/install-linking/redeem",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=redeem_body,
        request_headers={"Content-Type": "application/json"},
    )
    if status != 200:
        raise AssertionError(f"/api/v1/install-linking/redeem returned {status}: {body[:400]}")

    redeem = load_json_object(body, "/api/v1/install-linking/redeem")
    redeemed_installation_id = ((redeem.get("installation") or {}).get("installationId") if isinstance(redeem, dict) else None)
    if redeemed_installation_id != installation_id:
        raise AssertionError("install claim redemption did not bind the expected installation id")
    access_token = ((redeem.get("grant") or {}).get("accessToken") if isinstance(redeem, dict) else None)
    if not access_token:
        raise AssertionError("install claim redemption did not expose an installation grant access token")

    status, body, _, _ = fetch(
        base_url,
        "/api/v1/campaign-spine/me",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/api/v1/campaign-spine/me returned {status}, expected 200 after install claim")

    summary = load_json_object(body, "/api/v1/campaign-spine/me")
    claimed_devices = ((summary.get("restore") or {}).get("claimedDevices") or [])
    if not claimed_devices:
        raise AssertionError("install claim redemption did not surface a claimed device in restore")

    return summary, installation_id, str(access_token)


def verify_signed_in_work_audit(
    base_url: str,
    *,
    email: str,
    internal_token: str,
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

    summary, claimed_installation_id, current_grant_access_token = ensure_claimed_device(
        base_url,
        cookie_header=cookie_header,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
    )
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
    require_snippet(body, "Recent install handoffs", "/account/access")
    require_snippet(body, "Cross-device recovery", "/account/access")
    require_snippet(body, "Advanced device recovery", "/account/access")
    require_snippet(body, "Offline-ready return", "/account/access")
    require_snippet(body, "What stays on this device", "/account/access")
    require_snippet(body, "Open downloads", "/account/access")
    require_snippet(body, "How install linking works", "/account/access")
    require_snippet(body, "live-audit-host", "/account/access")
    require_snippet(body, "0.0-live-audit on preview", "/account/access")
    if current_grant_access_token in body:
        raise AssertionError("/account/access leaked the raw installation access token")

    status, body, _, _ = fetch(
        base_url,
        "/home/access",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/home/access returned {status}, expected 200")
    require_snippet(body, "What changed for you", "/home/access")
    require_snippet(body, "Release and device state", "/home/access")
    require_snippet(body, "Open Devices &amp; access", "/home/access")
    require_snippet(body, "Open what works today", "/home/access")

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
        "Stage travel prefetch",
        "Generate aftermath recap package",
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
    subject_id = extract_subject_id(body, workspace_path)
    support_index_path = "/account/support"
    status, body, _, _ = fetch(
        base_url,
        support_index_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{support_index_path} returned {status}, expected 200")
    require_snippet(body, "Need routing help first?", support_index_path)
    require_snippet(body, "Ask the grounded support assistant", support_index_path)
    require_snippet(body, "Submit support case", support_index_path)
    require_snippet(body, "Open or active cases", support_index_path)
    require_snippet(body, "Total recent cases", support_index_path)
    support_case_payload = json.dumps(
        {
            "kind": "bug_report",
            "title": SUPPORT_AUDIT_TITLE,
            "summary": SUPPORT_AUDIT_SUMMARY,
            "detail": f"{SUPPORT_AUDIT_DETAIL_PREFIX} Marker {time.time_ns()}.",
            "installationId": claimed_installation_id,
            "applicationVersion": "0.0-live-audit",
            "releaseChannel": "preview",
            "headId": "avalonia",
            "platform": "linux",
            "arch": "x64",
            "source": "hub_account",
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/support/cases",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=support_case_payload,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 202:
        raise AssertionError(f"/api/v1/support/cases returned {status}: {body[:400]}")

    support_case = load_json_object(body, "/api/v1/support/cases")
    support_case_id = str(support_case.get("caseId") or "")
    if not support_case_id:
        raise AssertionError("support case submission did not expose a case id")
    support_detail_path = f"/account/support/{quote(support_case_id, safe='')}"
    support_fixed_version = f"0.0-live-audit-fix-{time.time_ns()}"
    transition_payload = json.dumps(
        {
            "targetStatus": "released_to_reporter_channel",
            "note": f"Fix is live on preview {support_fixed_version}.",
            "fixedVersion": support_fixed_version,
            "fixedChannel": "preview",
            "actor": "fleet_automation",
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        f"/api/v1/support/cases/{quote(support_case_id, safe='')}/transition",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=transition_payload,
        request_headers={
            "Authorization": f"Bearer {internal_token}",
            "Content-Type": "application/json",
        },
    )
    if status != 200:
        raise AssertionError(f"/api/v1/support/cases/{support_case_id}/transition returned {status}: {body[:400]}")
    released_case = load_json_object(body, f"/api/v1/support/cases/{support_case_id}/transition")
    if released_case.get("status") != "released_to_reporter_channel":
        raise AssertionError("support case did not enter released_to_reporter_channel")

    assistant_release_payload = json.dumps(
        {
            "query": "Has the preview fix for my linked install shipped yet?",
            "installationId": claimed_installation_id,
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/support/cases/assistant",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=assistant_release_payload,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"/api/v1/support/cases/assistant pre-refresh returned {status}: {body[:400]}")
    released_assistant = load_json_object(body, "/api/v1/support/cases/assistant")
    require_snippet(str(released_assistant.get("answer") or ""), support_fixed_version, "/api/v1/support/cases/assistant")
    if not any(str(item.get("actionId") or "") == "open_downloads" for item in released_assistant.get("actions") or [] if isinstance(item, dict)):
        raise AssertionError("support assistant did not direct the reporter back to downloads before the fix build was installed")

    notify_payload = json.dumps(
        {
            "note": f"Reporter notified that preview {support_fixed_version} contains the fix.",
            "actor": "hub",
            "channel": "account_history",
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        f"/api/v1/support/cases/{quote(support_case_id, safe='')}/notify",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=notify_payload,
        request_headers={
            "Authorization": f"Bearer {internal_token}",
            "Content-Type": "application/json",
        },
    )
    if status != 200:
        raise AssertionError(f"/api/v1/support/cases/{support_case_id}/notify returned {status}: {body[:400]}")
    notified_case = load_json_object(body, f"/api/v1/support/cases/{support_case_id}/notify")
    if notified_case.get("status") != "user_notified":
        raise AssertionError("support case did not enter user_notified")

    status, body, _, _ = fetch(
        base_url,
        support_index_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{support_index_path} returned {status}, expected 200 after support-case notify")
    require_snippet(body, SUPPORT_AUDIT_TITLE, support_index_path)
    require_snippet(body, support_detail_path, support_index_path)
    require_snippet(body, "Need routing help first?", support_index_path)

    status, body, _, _ = fetch(
        base_url,
        support_detail_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{support_detail_path} returned {status}, expected 200")
    require_snippet(body, "Release progress:", support_detail_path)
    require_snippet(body, claimed_installation_id, support_detail_path)
    require_snippet(body, support_fixed_version, support_detail_path)
    require_snippet(body, "Update it to preview", support_detail_path)

    refresh_payload = json.dumps(
        {
            "installationId": claimed_installation_id,
            "accessToken": current_grant_access_token,
            "headId": "avalonia",
            "applicationVersion": support_fixed_version,
            "channelId": "preview",
            "platform": "linux",
            "arch": "x64",
            "publicKey": f"live-audit-public-key-{time.time_ns()}",
            "hostLabel": "live-audit-host",
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/install-linking/grants/refresh",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=refresh_payload,
        request_headers={"Content-Type": "application/json"},
    )
    if status != 200:
        raise AssertionError(f"/api/v1/install-linking/grants/refresh returned {status}: {body[:400]}")
    refresh_result = load_json_object(body, "/api/v1/install-linking/grants/refresh")
    if not refresh_result.get("rotated"):
        raise AssertionError("installation grant refresh did not rotate onto the reporter-ready fix build")
    refreshed_grant = refresh_result.get("grant") or {}
    current_grant_access_token = str((refreshed_grant.get("accessToken") if isinstance(refreshed_grant, dict) else "") or "")
    if not current_grant_access_token:
        raise AssertionError("installation grant refresh did not expose the next grant access token")

    status, body, _, _ = fetch(
        base_url,
        support_detail_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{support_detail_path} returned {status}, expected 200 after install refresh")
    require_snippet(body, "Fix worked here", support_detail_path)
    require_snippet(body, "Still broken", support_detail_path)
    require_snippet(body, support_fixed_version, support_detail_path)

    assistant_ready_payload = json.dumps(
        {
            "query": "Can I verify the preview fix on my linked install now?",
            "installationId": claimed_installation_id,
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/support/cases/assistant",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=assistant_ready_payload,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"/api/v1/support/cases/assistant verification-ready returned {status}: {body[:400]}")
    ready_assistant = load_json_object(body, "/api/v1/support/cases/assistant")
    require_snippet(str(ready_assistant.get("answer") or ""), "Use the verification buttons", "/api/v1/support/cases/assistant")
    ready_actions = [item for item in ready_assistant.get("actions") or [] if isinstance(item, dict)]
    verify_action = next((item for item in ready_actions if str(item.get("actionId") or "") == "verify_fix_on_case"), None)
    if verify_action is None:
        raise AssertionError("support assistant did not surface verify_fix_on_case once the linked install was ready")
    if str(verify_action.get("href") or "") != support_detail_path:
        raise AssertionError("support assistant did not route verify_fix_on_case back to the tracked account support detail")

    for signed_in_path in ("/downloads", "/now", "/help"):
        status, body, _, _ = fetch(
            base_url,
            signed_in_path,
            public_host=public_host,
            forwarded_proto=forwarded_proto,
            request_headers={"Cookie": cookie_header},
        )
        if status != 200:
            raise AssertionError(f"{signed_in_path} returned {status}, expected 200 for signed-in trust validation")
        require_snippet(body, "Recommended for this install", signed_in_path)
        require_snippet(body, "Install posture", signed_in_path)
        require_snippet(body, "trust-pulse-trend__point", signed_in_path)
        if body.count("Adoption health") < 2:
            raise AssertionError(f"{signed_in_path} should surface adoption health in both the install-specific trust panel and the weekly trust pulse")

    status, body, _, _ = fetch(
        base_url,
        "/downloads",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/downloads returned {status}, expected 200 for fix-ready trust validation")
    require_snippet(body, "Your linked install can verify a fix now", "/downloads")
    require_snippet(body, "fix worked here", "/downloads")

    verify_payload = json.dumps(
        {
            "outcome": "confirmed_fixed",
            "note": f"Preview {support_fixed_version} fixed it here.",
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        f"/api/v1/support/cases/{quote(support_case_id, safe='')}/verify",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=verify_payload,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"/api/v1/support/cases/{support_case_id}/verify returned {status}: {body[:400]}")
    verified_case = load_json_object(body, f"/api/v1/support/cases/{support_case_id}/verify")
    if verified_case.get("reporterVerificationState") != "confirmed_fixed":
        raise AssertionError("support case verification did not record a confirmed_fixed outcome")

    status, body, _, _ = fetch(
        base_url,
        support_detail_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{support_detail_path} returned {status}, expected 200 after reporter verification")
    require_snippet(body, "Closed and confirmed", support_detail_path)
    require_snippet(body, support_fixed_version, support_detail_path)

    status, body, _, _ = fetch(
        base_url,
        support_index_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{support_index_path} returned {status}, expected 200 after reporter verification")
    require_snippet(body, SUPPORT_AUDIT_TITLE, support_index_path)
    require_snippet(body, support_detail_path, support_index_path)
    require_snippet(body, "Total recent cases", support_index_path)
    require_snippet(body, "Need routing help first?", support_index_path)

    status, body, _, _ = fetch(
        base_url,
        "/home/access",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/home/access returned {status}, expected 200 after reporter verification")
    require_snippet(body, SUPPORT_AUDIT_TITLE, "/home/access")
    require_snippet(body, support_fixed_version, "/home/access")
    require_snippet(body, claimed_installation_id, "/home/access")
    require_snippet(body, "Open downloads", "/home/access")

    community_operations = summary.get("communityOperations") or []
    if not community_operations:
        raise AssertionError("/api/v1/campaign-spine/me did not expose any governed community operation")
    lead_operation = community_operations[0]
    group_id = lead_operation.get("groupId")
    if not group_id:
        raise AssertionError("lead community operation did not expose a group id")
    invite_campaigns = lead_operation.get("inviteCampaigns") or []
    join_code_body = json.dumps(
        {
            "subjectId": subject_id,
            "role": "member",
            "ttl": "7.00:00:00",
        }
    ).encode("utf-8")
    join_code_path = f"/api/v1/groups/{group_id}/join-codes"
    status, body, _, _ = fetch(
        base_url,
        join_code_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=join_code_body,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"{join_code_path} returned {status}: {body[:400]}")
    join_code = json.loads(body)
    if not join_code.get("code"):
        raise AssertionError("join-code issuance did not expose the issued code")

    missing_join_body = json.dumps(
        {
            "subjectId": subject_id,
            "code": f"JOIN-MISSING-{time.time_ns()}",
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/groups/join",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=missing_join_body,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 404:
        raise AssertionError(f"/api/v1/groups/join missing-code check returned {status}: {body[:400]}")
    require_snippet(body, "fresh join code", "/api/v1/groups/join")

    boost_code_body = json.dumps(
        {
            "subjectId": subject_id,
            "groupId": group_id,
            "campaignId": invite_campaigns[0]["campaignId"] if invite_campaigns else None,
            "label": "live_operator_audit",
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/boost-codes",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=boost_code_body,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"/api/v1/boost-codes returned {status}: {body[:400]}")
    boost_code = json.loads(body)
    if not boost_code.get("code"):
        raise AssertionError("boost-code issuance did not expose the issued code")

    sponsor_session_body = json.dumps(
        {
            "subjectId": subject_id,
            "projectId": "hub",
            "groupId": group_id,
            "subjectLabel": "Live Audit Operator",
            "campaignId": invite_campaigns[0]["campaignId"] if invite_campaigns else None,
            "visibility": "group",
            "requestedLaneType": "participant_burst",
            "requestedLaneRole": "coding",
            "authorizationTier": "plus",
            "tierSource": "operator_verified",
        }
    ).encode("utf-8")
    sponsor_session_path = "/api/v1/boost-sessions"
    status, body, _, _ = fetch(
        base_url,
        sponsor_session_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=sponsor_session_body,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"{sponsor_session_path} returned {status}: {body[:400]}")
    sponsor_session = json.loads(body)
    sponsor_session_id = sponsor_session.get("sponsorSessionId")
    if not sponsor_session_id:
        raise AssertionError("sponsor-session creation did not expose a sponsor session id")

    consent_path = f"/api/v1/boost-sessions/{sponsor_session_id}/consent"
    status, body, _, _ = fetch(
        base_url,
        consent_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=b"",
        request_headers={
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"{consent_path} returned {status}: {body[:400]}")
    sponsor_session = json.loads(body)
    if sponsor_session.get("status") != "consented":
        raise AssertionError("sponsor-session consent did not move the governed session into the consented state")

    status, body, _, _ = fetch(
        base_url,
        "/api/v1/campaign-spine/me",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/api/v1/campaign-spine/me returned {status}, expected 200 after sponsor-session creation")
    refreshed_summary = json.loads(body)
    refreshed_operations = refreshed_summary.get("communityOperations") or []
    refreshed_operation = next((item for item in refreshed_operations if item.get("groupId") == group_id), None)
    if refreshed_operation is None:
        raise AssertionError("signed-in campaign summary lost the lead community operation after sponsor-session creation")
    refreshed_sponsor_sessions = refreshed_operation.get("recentSponsorSessions") or []
    refreshed_sponsor_session = next((item for item in refreshed_sponsor_sessions if item.get("sponsorSessionId") == sponsor_session_id), None)
    if refreshed_sponsor_session is None:
        raise AssertionError("signed-in campaign summary did not surface the new sponsor session on the operator rail")

    missing_boost_body = json.dumps(
        {
            "subjectId": subject_id,
            "code": f"BOOST-MISSING-{time.time_ns()}",
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/boost-codes/redeem",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=missing_boost_body,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 404:
        raise AssertionError(f"/api/v1/boost-codes/redeem missing-code check returned {status}: {body[:400]}")
    require_snippet(body, "fresh sponsorship code", "/api/v1/boost-codes/redeem")

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

    travel_prefetch_body = json.dumps(
        {
            "installationId": claimed_installation_id,
            "note": "Signed-in live audit staging the exact offline set.",
        }
    ).encode("utf-8")
    travel_prefetch_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/travel-prefetches"
    status, body, _, _ = fetch(
        base_url,
        travel_prefetch_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=travel_prefetch_body,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"{travel_prefetch_path} returned {status}: {body[:400]}")

    travel_prefetch = json.loads(body)
    if not travel_prefetch.get("receiptId"):
        raise AssertionError("travel prefetch response did not expose a receipt id")

    aftermath_body = json.dumps(
        {
            "runId": target_run.get("runId"),
            "packageKind": "session_recap",
            "note": "Signed-in live audit pinning aftermath recap truth to the shared return lane.",
        }
    ).encode("utf-8")
    aftermath_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/aftermath-recap-packages"
    status, body, _, _ = fetch(
        base_url,
        aftermath_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=aftermath_body,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"{aftermath_path} returned {status}: {body[:400]}")

    aftermath_package = json.loads(body)
    if not aftermath_package.get("packageId"):
        raise AssertionError("aftermath recap response did not expose a package id")

    downtime_body = json.dumps(
        {
            "runId": target_run.get("runId"),
            "packageKind": "downtime_brief",
            "note": "Signed-in live audit pinning downtime follow-through to the shared return lane.",
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        aftermath_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=downtime_body,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"{aftermath_path} downtime brief returned {status}: {body[:400]}")

    downtime_package = json.loads(body)
    if not downtime_package.get("packageId"):
        raise AssertionError("downtime brief response did not expose a package id")

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
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/campaign-spine/me",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/api/v1/campaign-spine/me returned {status}, expected 200 after roster transfer")
    post_transfer_summary = json.loads(body)
    post_transfer_operations = post_transfer_summary.get("communityOperations") or []
    post_transfer_operation = next((item for item in post_transfer_operations if item.get("groupId") == group_id), None)
    if post_transfer_operation is None:
        raise AssertionError("signed-in campaign summary lost the operator rail after the roster transfer")

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
    require_snippet(body, "Prep launch audit", "/account/work")
    require_snippet(body, "Operations pulse", "/account/work")
    require_snippet(body, "League / season operations", "/account/work")
    require_snippet(body, "Season / event pulse", "/account/work")
    require_snippet(body, "Season &amp; event rail", "/account/work")
    require_snippet(body, "Season board", "/account/work")
    require_snippet(body, "Invite &amp; sponsorship rail", "/account/work")
    require_snippet(body, "Issue governed join code", "/account/work")
    require_snippet(body, "Issue governed boost code", "/account/work")
    require_snippet(body, "Recent join codes", "/account/work")
    require_snippet(body, "Recent boost codes", "/account/work")
    require_snippet(body, "Recent sponsor sessions", "/account/work")
    require_snippet(body, join_code["code"], "/account/work")
    require_snippet(body, boost_code["code"], "/account/work")
    require_snippet(body, post_transfer_operation["leagueOperationsSummary"], "/account/work")
    require_snippet(body, refreshed_sponsor_session["userDisplayName"], "/account/work")
    require_snippet(body, refreshed_sponsor_session["campaignName"], "/account/work")
    require_snippet(body, "Member guidance rail", "/account/work")
    require_snippet(body, "Open shared campaign view", "/account/work")
    require_snippet(body, "Open current release", "/account/work")
    require_snippet(body, "Open downloads", "/account/work")
    require_snippet(body, "Open help and trust", "/account/work")
    require_snippet(body, "Open support closure", "/account/work")
    run_detail_path = extract_first_match(
        body,
        r'href="([^"]*/account/work/runs/[^"]+)"',
        "/account/work",
        "run detail link")
    rules_detail_path = extract_first_match(
        body,
        r'href="([^"]*/account/work/rules/[^"]+)"',
        "/account/work",
        "rules detail link")
    status, body, _, _ = fetch(
        base_url,
        "/home/work",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/home/work returned {status}, expected 200")
    require_snippet(body, "Next-session carry-forward", "/home/work")
    require_snippet(body, "Open next-session return", "/home/work")
    require_snippet(body, "Aftermath recap", "/home/work")
    require_snippet(body, aftermath_package["title"], "/home/work")
    require_snippet(body, "Open aftermath and return", "/home/work")
    require_snippet(body, "Downtime brief", "/home/work")
    require_snippet(body, downtime_package["title"], "/home/work")
    require_snippet(body, "Open downtime brief", "/home/work")
    require_snippet(body, "Roster move", "/home/work")
    require_snippet(body, transfer["runnerHandle"], "/home/work")
    require_snippet(body, "Open governed roster moves", "/home/work")
    require_snippet(body, "Operator posture", "/home/work")
    require_snippet(body, "Season / event pulse", "/home/work")
    require_snippet(body, "Latest event:", "/home/work")
    require_snippet(body, "Board:", "/home/work")
    require_snippet(body, "League:", "/home/work")
    require_snippet(body, "Invites:", "/home/work")
    require_snippet(body, "Sponsors:", "/home/work")
    require_snippet(body, "Guide: current preview, downloads, and closure posture stay on the same operator rail.", "/home/work")
    require_snippet(body, "Open league rail", "/home/work")
    require_snippet(body, "Open season board", "/home/work")
    require_snippet(body, "Open invite rail", "/home/work")
    require_snippet(body, "Open sponsor rail", "/home/work")
    require_snippet(body, "Open member guidance", "/home/work")
    require_snippet(body, "Consequence watch", "/home/work")
    require_snippet(body, prep_launch["packetTitle"], "/home/work")
    require_snippet(body, travel_prefetch["deviceRole"], "/home/work")
    require_snippet(body, post_transfer_operation["leagueOperationsSummary"], "/home/work")
    require_snippet(body, refreshed_sponsor_session["campaignName"], "/home/work")
    home_workspace_path = extract_first_match(
        body,
        r'href="([^"]*/account/work/workspaces/[^"#?]+)"',
        "/home/work",
        "home workspace detail link")
    home_build_handoff_path = extract_first_match(
        body,
        r'href="([^"]*/account/work/build-handoffs/[^"]+)"',
        "/home/work",
        "home build handoff detail link")
    home_rules_detail_path = extract_first_match(
        body,
        r'href="([^"]*/account/work/rules/[^"]+)"',
        "/home/work",
        "home rules detail link")
    home_publication_detail_path = extract_first_match(
        body,
        r'href="([^"]*/account/work/publications/[^"]+)"',
        "/home/work",
        "home publication detail link")
    home_next_session_path = extract_first_match(
        body,
        r'href="([^"]*#selected-next-session-carry-forward)"',
        "/home/work",
        "home next-session return link")
    home_first_playable_path = extract_optional_match(body, r'href="([^"]*#selected-first-playable-session)"')
    home_aftermath_path = extract_first_match(
        body,
        r'href="([^"]*#aftermath-packages)"',
        "/home/work",
        "home aftermath return link")
    home_downtime_path = extract_first_match(
        body,
        r'href="([^"]*#selected-downtime-brief)"',
        "/home/work",
        "home downtime brief link")
    home_campaign_memory_path = extract_first_match(
        body,
        r'href="([^"]*#selected-campaign-memory)"',
        "/home/work",
        "home campaign-memory link")
    home_roster_moves_path = extract_first_match(
        body,
        r'href="([^"]*/account/work#community-ops)"',
        "/home/work",
        "home governed roster-moves link")
    home_member_guidance_path = extract_first_match(
        body,
        r'href="([^"]*#community-op-guidance-[^"]+)"',
        "/home/work",
        "home member-guidance link")
    home_league_rail_path = extract_first_match(
        body,
        r'href="([^"]*#community-op-league-[^"]+)"',
        "/home/work",
        "home league-rail link")
    home_season_board_path = extract_first_match(
        body,
        r'href="([^"]*#community-op-board-[^"]+)"',
        "/home/work",
        "home season-board link")
    home_invite_rail_path = extract_first_match(
        body,
        r'href="([^"]*#community-op-invites-[^"]+)"',
        "/home/work",
        "home invite-rail link")
    home_sponsor_rail_path = extract_first_match(
        body,
        r'href="([^"]*#community-op-sponsor-sessions-[^"]+)"',
        "/home/work",
        "home sponsor-rail link")
    fetch_fragment_target(
        base_url,
        home_workspace_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("What changed for me", "Support follow-through", "Artifact shelf posture"),
    )
    fetch_fragment_target(
        base_url,
        home_build_handoff_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("Build follow-through", "Variant", "Progression"),
    )
    fetch_fragment_target(
        base_url,
        home_rules_detail_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("Grounded rule answer", "Before", "After", "Provenance"),
    )
    fetch_fragment_target(
        base_url,
        home_publication_detail_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("Publication status", "Trust", "Discovery", "Status"),
    )
    fetch_fragment_target(
        base_url,
        home_next_session_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("Next-session carry-forward", "Carry-forward summary"),
    )
    if home_first_playable_path:
        fetch_fragment_target(
            base_url,
            home_first_playable_path,
            public_host=public_host,
            forwarded_proto=forwarded_proto,
            cookie_header=cookie_header,
            required_texts=("First playable session", "Session summary"),
        )
    fetch_fragment_target(
        base_url,
        home_aftermath_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("Aftermath and recap", "Recent aftermath recap packages"),
    )
    fetch_fragment_target(
        base_url,
        home_downtime_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("Downtime brief", "Next-session return"),
    )
    fetch_fragment_target(
        base_url,
        home_campaign_memory_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("Campaign memory", "Return lane"),
    )
    fetch_fragment_target(
        base_url,
        home_roster_moves_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("Teams &amp; permissions", "Recent governed roster moves"),
    )
    fetch_fragment_target(
        base_url,
        home_member_guidance_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("Member guidance rail", "Current preview posture"),
    )
    fetch_fragment_target(
        base_url,
        home_league_rail_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("League / season operations", "Campaign return pulse"),
    )
    fetch_fragment_target(
        base_url,
        home_season_board_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("Season board", "Open shared campaign view"),
    )
    fetch_fragment_target(
        base_url,
        home_invite_rail_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("Invite &amp; sponsorship rail", "Issue governed join code", "Issue governed boost code"),
    )
    fetch_fragment_target(
        base_url,
        home_sponsor_rail_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        cookie_header=cookie_header,
        required_texts=("Recent sponsor sessions",),
    )
    status, body, _, _ = fetch(
        base_url,
        workspace_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_path} returned {status}, expected 200 after prep launch")
    require_snippet(body, "Next-session carry-forward", workspace_path)
    require_snippet(body, "Recent governed prep launches", workspace_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_path)
    require_snippet(body, "Recent travel prefetch receipts", workspace_path)
    require_snippet(body, travel_prefetch["deviceRole"], workspace_path)
    require_snippet(body, "Recent aftermath recap packages", workspace_path)
    require_snippet(body, aftermath_package["title"], workspace_path)
    require_snippet(body, downtime_package["title"], workspace_path)
    require_snippet(body, "Downtime brief", workspace_path)
    require_snippet(body, "Artifact shelf posture", workspace_path)
    require_snippet(body, "Audience:", workspace_path)
    require_snippet(body, "Ownership:", workspace_path)
    require_snippet(body, "Publication:", workspace_path)
    require_snippet(body, "Open publication status", workspace_path)
    workspace_search_path = f"{workspace_path}?prepQuery=opposition"
    status, body, _, _ = fetch(
        base_url,
        workspace_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_search_path)
    require_snippet(body, 'match(es) for "opposition"', workspace_search_path)
    require_snippet(body, "Recent governed prep launches", workspace_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_search_path)
    require_snippet(body, "Recent travel prefetch receipts", workspace_search_path)
    require_snippet(body, travel_prefetch["deviceRole"], workspace_search_path)
    require_snippet(body, "Recent aftermath recap packages", workspace_search_path)
    require_snippet(body, aftermath_package["title"], workspace_search_path)
    require_snippet(body, "Next-session carry-forward", workspace_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_search_path} should return at least one governed prep packet for the opposition query")
    publication_detail_path = extract_first_match(
        body,
        r'href="([^"]*/account/work/publications/[^"]+)"',
        workspace_search_path,
        "publication status link")
    status, body, _, _ = fetch(
        base_url,
        publication_detail_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{publication_detail_path} returned {status}, expected 200")
    require_snippet(body, "Publication status", publication_detail_path)
    require_snippet(body, "Trust", publication_detail_path)
    require_snippet(body, "Discovery", publication_detail_path)
    require_snippet(body, "Status", publication_detail_path)
    require_snippet(body, "Open build path for", publication_detail_path)
    build_handoff_detail_path = extract_first_match(
        body,
        r'href="([^"]*/account/work/build-handoffs/[^"]+)"',
        publication_detail_path,
        "build handoff detail link")
    status, body, _, _ = fetch(
        base_url,
        build_handoff_detail_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{build_handoff_detail_path} returned {status}, expected 200")
    require_snippet(body, "Build follow-through", build_handoff_detail_path)
    require_snippet(body, "Variant", build_handoff_detail_path)
    require_snippet(body, "Progression", build_handoff_detail_path)
    require_snippet(body, "Next safe action", build_handoff_detail_path)
    require_snippet(body, "Runtime", build_handoff_detail_path)
    require_snippet(body, "Return", build_handoff_detail_path)
    require_snippet(body, "Support", build_handoff_detail_path)
    require_snippet(body, "Planner coverage", build_handoff_detail_path)
    status, body, _, _ = fetch(
        base_url,
        run_detail_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{run_detail_path} returned {status}, expected 200")
    require_snippet(body, "Run context", run_detail_path)
    require_snippet(body, "Status", run_detail_path)
    require_snippet(body, "Active scene", run_detail_path)
    require_snippet(body, "Objectives", run_detail_path)
    require_snippet(body, "Scenes", run_detail_path)
    require_snippet(body, "Continuity:", run_detail_path)
    status, body, _, _ = fetch(
        base_url,
        rules_detail_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{rules_detail_path} returned {status}, expected 200")
    require_snippet(body, "Grounded rule answer", rules_detail_path)
    require_snippet(body, "Before", rules_detail_path)
    require_snippet(body, "After", rules_detail_path)
    require_snippet(body, "Provenance", rules_detail_path)
    require_snippet(body, "Evidence:", rules_detail_path)
    print(
        "ok signed-in /account/work -> "
        f"{final_url} workspace={workspace_id} install={claimed_installation_id} support_case={support_case_id} support_fix={support_fixed_version} join_code={join_code['code']} boost_code={boost_code['code']} sponsor_session={sponsor_session_id} prep_launch={prep_launch['launchId']} travel_prefetch={travel_prefetch['receiptId']} aftermath={aftermath_package['packageId']} downtime={downtime_package['packageId']} transfer={transfer['transferId']} runner={transfer['runnerHandle']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the public Chummer Hub surface.")
    parser.add_argument("--base-url", default="https://chummer.run", help="Base URL to audit.")
    parser.add_argument("--public-host", default=None, help="Optional Host header for reverse-proxied local edge checks.")
    parser.add_argument("--forwarded-proto", default=None, help="Optional X-Forwarded-Proto header for reverse-proxied local edge checks.")
    parser.add_argument("--verify-http-redirects", action="store_true", help="Verify that the local HTTP edge redirects to the public HTTPS host.")
    parser.add_argument("--verify-signed-in-work", action="store_true", help="Verify the signed-in account/work journey, including governed support verification, roster transfer, and operator live actions.")
    parser.add_argument("--signed-in-email", default=None, help="Optional example.invalid email used for the signed-in work audit. Defaults to a generated value.")
    parser.add_argument("--internal-token", default=None, help="Optional internal support automation bearer token for signed-in support verification.")
    parser.add_argument("--compose-file", default="docker-compose.public-edge.yml", help="Compose file used to resolve FLEET_INTERNAL_API_TOKEN when --verify-signed-in-work is enabled.")
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
            required_texts=("What you can verify now", "Build, explain, and run with visible evidence", "Who can get it now", "Progress trend", "Adoption health", "trust-pulse-trend__point", "Status guide"),
            expects_header_count=1),
        AuditRoute(
            "/downloads",
            "Install the current preview",
            required_texts=("Create account to get preview", "Already have an account? Sign in", "Advanced download options", "Release notes, known issues, and requirements", "Who can get it now", "Progress trend", "Adoption health", "trust-pulse-trend__point"),
            forbidden_texts=("Package details",),
            expects_header_count=1),
        AuditRoute("/horizons", "What Chummer is building toward", required_texts=("Preparing next", "Designing in public", "Research track", "Status guide"), forbidden_texts=("Research tracks",), expects_header_count=1),
        AuditRoute("/artifacts", "Current proof surfaces", required_texts=("Preview in progress", "Status guide", "Anyone evaluating the preview"), expects_header_count=1),
        AuditRoute("/artifacts/current-preview-build", "Current preview build", required_texts=("Anyone evaluating the preview",), forbidden_texts=(">public<",), expects_header_count=1),
        AuditRoute("/roadmap/nexus-pan", "NEXUS-PAN", required_texts=("Anyone evaluating the preview",), forbidden_texts=(">public<",), expects_header_count=1),
        AuditRoute("/participate", "Choose how to participate", expects_header_count=1),
        AuditRoute("/help", "Get help without guessing", required_texts=("Fallback:", "Support, survey, and assistant data stay on a bounded clock", "Who can get it now", "Progress trend", "Adoption health", "trust-pulse-trend__point"), expects_header_count=1),
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
    pulse_payload = load_json_object(body, "/api/public/weekly-pulse")
    if status != 200 or str(pulse_payload.get("contract_name") or "").strip() != "chummer.weekly_product_pulse":
        raise AssertionError("/api/public/weekly-pulse did not serve the mirrored weekly pulse artifact")

    journey_gate_health = pulse_payload.get("journey_gate_health")
    if not isinstance(journey_gate_health, dict):
        raise AssertionError("/api/public/weekly-pulse is missing journey_gate_health")
    if str(journey_gate_health.get("state") or "").strip().lower() != "ready":
        raise AssertionError("/api/public/weekly-pulse did not reflect the current Fleet ready-state journey proof")
    if int(journey_gate_health.get("blocked_count") or 0) != 0:
        raise AssertionError("/api/public/weekly-pulse still reports blocked journey gates")

    supporting_signals = pulse_payload.get("supporting_signals")
    if not isinstance(supporting_signals, dict):
        raise AssertionError("/api/public/weekly-pulse is missing supporting_signals")
    for key in ("closure_health", "adoption_health", "progress_trend", "provider_route_stewardship"):
        if not isinstance(supporting_signals.get(key), dict):
            raise AssertionError(f"/api/public/weekly-pulse is missing supporting_signals.{key}")

    launch_readiness = str(supporting_signals.get("launch_readiness") or "").strip()
    if not launch_readiness:
        raise AssertionError("/api/public/weekly-pulse is missing supporting_signals.launch_readiness")
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
        internal_token = resolve_internal_token(args.internal_token, args.compose_file)
        signed_in_email = args.signed_in_email or f"live-audit-{time.time_ns()}@example.invalid"
        verify_signed_in_work_audit(
            args.base_url,
            email=signed_in_email,
            internal_token=internal_token,
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
