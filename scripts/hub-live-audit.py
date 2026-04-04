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
DEFAULT_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36 ChummerHubLiveAudit/1.0"
    ),
    "Accept": "text/html,application/json,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


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
        headers = dict(DEFAULT_REQUEST_HEADERS)
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


def is_public_creator_publication_path(path: str) -> bool:
    lowered = path.lower()
    return "/artifacts/publications/" in lowered or "/artifacts/creator/" in lowered


def require_creator_publication_body(body: str, path: str) -> None:
    if is_public_creator_publication_path(path):
        for snippet in (
            "Governed publication discovery",
            "Public shared publication",
            "Why this publication is live",
            "Publication kind",
            "Provenance",
            "Trust",
            "Discovery",
            "Back to publication discovery",
            "Open artifacts shelf",
        ):
            require_snippet(body, snippet, path)
        return

    for snippet in (
        "Publication status",
        "Publication kind",
        "Trust",
        "Trust ranking",
        "Discovery",
        "Discoverable now",
        "Status",
        "Open build path for",
    ):
        require_snippet(body, snippet, path)


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
        "/account",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/account returned {status}, expected 200")
    require_snippet(body, "Keep the visible identity clear, stable, and easy to recognize.", "/account")
    require_snippet(body, "Display name", "/account")
    require_snippet(body, "Handle", "/account")
    require_snippet(body, "Timezone", "/account")
    require_snippet(body, "Save profile", "/account")
    require_snippet(body, "Primary sign-in", "/account")
    require_snippet(body, "Recovery email", "/account")
    require_snippet(body, "Start verification", "/account")

    status, body, _, _ = fetch(
        base_url,
        "/participate/codex",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/participate/codex returned {status}, expected 200")
    require_snippet(body, "Help Chummer show its work.", "/participate/codex")
    require_snippet(body, "I want to participate", "/participate/codex")
    require_snippet(body, "One decision, one code, one clean handoff", "/participate/codex")
    require_snippet(body, "Generate fresh code", "/participate/codex")
    require_snippet(body, "Open a fresh contribution lane", "/participate/codex")
    require_snippet(body, "Technical details and controls", "/participate/codex")

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
        "/account/settings",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/account/settings returned {status}, expected 200")
    require_snippet(body, "Choose what stays visible while deeper identifiers remain tucked away.", "/account/settings")
    require_snippet(body, "Visibility", "/account/settings")
    require_snippet(body, "Recovery posture", "/account/settings")
    require_snippet(body, "Provider-backed help", "/account/settings")
    require_snippet(body, "Open help", "/account/settings")
    require_snippet(body, "Read privacy", "/account/settings")
    require_snippet(body, "Read terms", "/account/settings")
    require_snippet(body, "Contact Chummer", "/account/settings")

    status, body, _, _ = fetch(
        base_url,
        "/account/advanced",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/account/advanced returned {status}, expected 200")
    require_snippet(body, "Hub account id", "/account/advanced")
    require_snippet(body, "Primary auth", "/account/advanced")
    require_snippet(body, "Linked identities", "/account/advanced")
    require_snippet(body, "Linked channels", "/account/advanced")
    require_snippet(body, "Recovery posture", "/account/advanced")
    require_snippet(body, "Follow horizons", "/account/advanced")

    status, body, _, _ = fetch(
        base_url,
        "/home",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/home returned {status}, expected 200")
    require_snippet(body, "Welcome back", "/home")
    require_snippet(body, "Use the current preview", "/home")
    require_snippet(body, "Keep this copy connected", "/home")
    require_snippet(body, "Open current release", "/home")

    status, body, _, _ = fetch(
        base_url,
        "/home/setup",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"/home/setup returned {status}, expected 200")
    require_snippet(body, "Finish the small setup flow, then come back to access and work", "/home/setup")
    require_snippet(body, "Open account settings instead", "/home/setup")
    require_snippet(body, "Finish the account basics", "/home/setup")
    require_snippet(body, "Name and timezone", "/home/setup")
    require_snippet(body, "What you want from Chummer", "/home/setup")
    require_snippet(body, "Backup sign-in and updates", "/home/setup")

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
    assistant_build_payload = json.dumps(
        {
            "query": "What is the safest build handoff before I export this dossier back into the campaign?",
            "installationId": claimed_installation_id,
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/support/cases/assistant",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=assistant_build_payload,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"/api/v1/support/cases/assistant build-truth check returned {status}: {body[:400]}")
    build_assistant = load_json_object(body, "/api/v1/support/cases/assistant")
    build_citations = [item for item in build_assistant.get("citations") or [] if isinstance(item, dict)]
    if not any(str(item.get("sourceKind") or "") == "build_truth" for item in build_citations):
        raise AssertionError("support assistant did not surface build-truth citations for the signed-in build-handoff question")
    build_actions = [item for item in build_assistant.get("actions") or [] if isinstance(item, dict)]
    if not any(str(item.get("actionId") or "") == "open_work" for item in build_actions):
        raise AssertionError("support assistant did not route the signed-in build-handoff question back to /account/work")
    assistant_rules_payload = json.dumps(
        {
            "query": "Why did the rule environment change for my campaign visibility posture?",
            "installationId": claimed_installation_id,
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/support/cases/assistant",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=assistant_rules_payload,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"/api/v1/support/cases/assistant rules-truth check returned {status}: {body[:400]}")
    rules_assistant = load_json_object(body, "/api/v1/support/cases/assistant")
    rules_citations = [item for item in rules_assistant.get("citations") or [] if isinstance(item, dict)]
    if not any(str(item.get("sourceKind") or "") == "rules_truth" for item in rules_citations):
        raise AssertionError("support assistant did not surface rules-truth citations for the signed-in rule-environment question")
    rules_actions = [item for item in rules_assistant.get("actions") or [] if isinstance(item, dict)]
    if not any(str(item.get("actionId") or "") == "open_home" for item in rules_actions):
        raise AssertionError("support assistant did not route the signed-in rule-environment question back to /home")
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
    assistant_case_payload = json.dumps(
        {
            "query": SUPPORT_AUDIT_TITLE,
            "installationId": claimed_installation_id,
            "caseId": support_case_id,
        }
    ).encode("utf-8")
    status, body, _, _ = fetch(
        base_url,
        "/api/v1/support/cases/assistant",
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        method="POST",
        body=assistant_case_payload,
        request_headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "RequestVerificationToken": workspace_token,
        },
    )
    if status != 200:
        raise AssertionError(f"/api/v1/support/cases/assistant case-truth check returned {status}: {body[:400]}")
    case_truth_assistant = load_json_object(body, "/api/v1/support/cases/assistant")
    case_truth_citations = [item for item in case_truth_assistant.get("citations") or [] if isinstance(item, dict)]
    if not any(str(item.get("sourceKind") or "") == "support_case" for item in case_truth_citations):
        raise AssertionError("support assistant did not cite the newly filed support case on the signed-in support route")
    case_truth_actions = [item for item in case_truth_assistant.get("actions") or [] if isinstance(item, dict)]
    if not any(str(item.get("actionId") or "") == "open_account_support" for item in case_truth_actions):
        raise AssertionError("support assistant did not route the newly filed support case back to the signed-in support timeline")
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
    prep_library_oppositions_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=oppositions"
    status, body, _, _ = fetch(
        base_url,
        prep_library_oppositions_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_oppositions_path} returned {status}, expected 200")

    prep_library_oppositions = json.loads(body)
    if not (prep_library_oppositions.get("items") or []):
        raise AssertionError("prep-library oppositions search did not expose any governed packet")
    prep_library_encounter_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=encounter"
    status, body, _, _ = fetch(
        base_url,
        prep_library_encounter_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_encounter_path} returned {status}, expected 200")

    prep_library_encounter = json.loads(body)
    if not (prep_library_encounter.get("items") or []):
        raise AssertionError("prep-library encounter search did not expose any governed packet")
    prep_library_enemy_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=enemy"
    status, body, _, _ = fetch(
        base_url,
        prep_library_enemy_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_enemy_path} returned {status}, expected 200")

    prep_library_enemy = json.loads(body)
    if not (prep_library_enemy.get("items") or []):
        raise AssertionError("prep-library enemy search did not expose any governed packet")
    prep_library_hostile_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=hostile"
    status, body, _, _ = fetch(
        base_url,
        prep_library_hostile_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_hostile_path} returned {status}, expected 200")

    prep_library_hostile = json.loads(body)
    if not (prep_library_hostile.get("items") or []):
        raise AssertionError("prep-library hostile search did not expose any governed packet")
    prep_library_adversary_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=adversary"
    status, body, _, _ = fetch(
        base_url,
        prep_library_adversary_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_adversary_path} returned {status}, expected 200")

    prep_library_adversary = json.loads(body)
    if not (prep_library_adversary.get("items") or []):
        raise AssertionError("prep-library adversary search did not expose any governed packet")
    prep_library_threat_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=threat"
    status, body, _, _ = fetch(
        base_url,
        prep_library_threat_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_threat_path} returned {status}, expected 200")

    prep_library_threat = json.loads(body)
    if not (prep_library_threat.get("items") or []):
        raise AssertionError("prep-library threat search did not expose any governed packet")
    prep_library_opfor_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=opfor"
    status, body, _, _ = fetch(
        base_url,
        prep_library_opfor_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_opfor_path} returned {status}, expected 200")

    prep_library_opfor = json.loads(body)
    if not (prep_library_opfor.get("items") or []):
        raise AssertionError("prep-library opfor search did not expose any governed packet")
    prep_library_opforce_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=opforce"
    status, body, _, _ = fetch(
        base_url,
        prep_library_opforce_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_opforce_path} returned {status}, expected 200")

    prep_library_opforce = json.loads(body)
    if not (prep_library_opforce.get("items") or []):
        raise AssertionError("prep-library opforce search did not expose any governed packet")
    prep_library_opforces_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=opforces"
    status, body, _, _ = fetch(
        base_url,
        prep_library_opforces_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_opforces_path} returned {status}, expected 200")

    prep_library_opforces = json.loads(body)
    if not (prep_library_opforces.get("items") or []):
        raise AssertionError("prep-library opforces search did not expose any governed packet")
    prep_library_opfors_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=opfors"
    status, body, _, _ = fetch(
        base_url,
        prep_library_opfors_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_opfors_path} returned {status}, expected 200")

    prep_library_opfors = json.loads(body)
    if not (prep_library_opfors.get("items") or []):
        raise AssertionError("prep-library opfors search did not expose any governed packet")
    prep_library_op_force_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=op-force"
    status, body, _, _ = fetch(
        base_url,
        prep_library_op_force_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_op_force_path} returned {status}, expected 200")

    prep_library_op_force = json.loads(body)
    if not (prep_library_op_force.get("items") or []):
        raise AssertionError("prep-library op-force search did not expose any governed packet")
    prep_library_op_space_force_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=op%20force"
    status, body, _, _ = fetch(
        base_url,
        prep_library_op_space_force_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_op_space_force_path} returned {status}, expected 200")

    prep_library_op_space_force = json.loads(body)
    if not (prep_library_op_space_force.get("items") or []):
        raise AssertionError("prep-library op force search did not expose any governed packet")

    prep_library_season_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=seasonops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_season_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_season_path} returned {status}, expected 200")

    prep_library_season = json.loads(body)
    if not (prep_library_season.get("items") or []):
        raise AssertionError("prep-library seasonops search did not expose any governed packet")
    prep_library_seasonop_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=seasonop"
    status, body, _, _ = fetch(
        base_url,
        prep_library_seasonop_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_seasonop_path} returned {status}, expected 200")

    prep_library_seasonop = json.loads(body)
    if not (prep_library_seasonop.get("items") or []):
        raise AssertionError("prep-library seasonop search did not expose any governed packet")
    prep_library_season_operation_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=season-operation"
    status, body, _, _ = fetch(
        base_url,
        prep_library_season_operation_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_season_operation_path} returned {status}, expected 200")

    prep_library_season_operation = json.loads(body)
    if not (prep_library_season_operation.get("items") or []):
        raise AssertionError("prep-library season-operation search did not expose any governed packet")
    prep_library_season_operations_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=season-operations"
    status, body, _, _ = fetch(
        base_url,
        prep_library_season_operations_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_season_operations_path} returned {status}, expected 200")

    prep_library_season_operations = json.loads(body)
    if not (prep_library_season_operations.get("items") or []):
        raise AssertionError("prep-library season-operations search did not expose any governed packet")
    prep_library_seasoncontrol_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=seasoncontrol"
    status, body, _, _ = fetch(
        base_url,
        prep_library_seasoncontrol_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_seasoncontrol_path} returned {status}, expected 200")

    prep_library_seasoncontrol = json.loads(body)
    if not (prep_library_seasoncontrol.get("items") or []):
        raise AssertionError("prep-library seasoncontrol search did not expose any governed packet")
    prep_library_season_control_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=season%20control"
    status, body, _, _ = fetch(
        base_url,
        prep_library_season_control_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_season_control_path} returned {status}, expected 200")

    prep_library_season_control = json.loads(body)
    if not (prep_library_season_control.get("items") or []):
        raise AssertionError("prep-library season control search did not expose any governed packet")
    prep_library_seasoncontrols_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=seasoncontrols"
    status, body, _, _ = fetch(
        base_url,
        prep_library_seasoncontrols_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_seasoncontrols_path} returned {status}, expected 200")

    prep_library_seasoncontrols = json.loads(body)
    if not (prep_library_seasoncontrols.get("items") or []):
        raise AssertionError("prep-library seasoncontrols search did not expose any governed packet")
    prep_library_seasonctrl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=seasonctrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_seasonctrl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_seasonctrl_path} returned {status}, expected 200")

    prep_library_seasonctrl = json.loads(body)
    if not (prep_library_seasonctrl.get("items") or []):
        raise AssertionError("prep-library seasonctrl search did not expose any governed packet")
    prep_library_seasonctl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=seasonctl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_seasonctl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_seasonctl_path} returned {status}, expected 200")

    prep_library_seasonctl = json.loads(body)
    if not (prep_library_seasonctl.get("items") or []):
        raise AssertionError("prep-library seasonctl search did not expose any governed packet")
    prep_library_seasonctls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=seasonctls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_seasonctls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_seasonctls_path} returned {status}, expected 200")

    prep_library_seasonctls = json.loads(body)
    if not (prep_library_seasonctls.get("items") or []):
        raise AssertionError("prep-library seasonctls search did not expose any governed packet")
    prep_library_season_ctls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=season%20ctls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_season_ctls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_season_ctls_path} returned {status}, expected 200")

    prep_library_season_ctls = json.loads(body)
    if not (prep_library_season_ctls.get("items") or []):
        raise AssertionError("prep-library season ctls search did not expose any governed packet")
    prep_library_seasonctrls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=seasonctrls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_seasonctrls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_seasonctrls_path} returned {status}, expected 200")

    prep_library_seasonctrls = json.loads(body)
    if not (prep_library_seasonctrls.get("items") or []):
        raise AssertionError("prep-library seasonctrls search did not expose any governed packet")
    prep_library_eventcontrol_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=eventcontrol"
    status, body, _, _ = fetch(
        base_url,
        prep_library_eventcontrol_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_eventcontrol_path} returned {status}, expected 200")

    prep_library_eventcontrol = json.loads(body)
    if not (prep_library_eventcontrol.get("items") or []):
        raise AssertionError("prep-library eventcontrol search did not expose any governed packet")
    prep_library_eventcontrols_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=eventcontrols"
    status, body, _, _ = fetch(
        base_url,
        prep_library_eventcontrols_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_eventcontrols_path} returned {status}, expected 200")

    prep_library_eventcontrols = json.loads(body)
    if not (prep_library_eventcontrols.get("items") or []):
        raise AssertionError("prep-library eventcontrols search did not expose any governed packet")
    prep_library_event_control_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=event%20control"
    status, body, _, _ = fetch(
        base_url,
        prep_library_event_control_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_event_control_path} returned {status}, expected 200")

    prep_library_event_control = json.loads(body)
    if not (prep_library_event_control.get("items") or []):
        raise AssertionError("prep-library event control search did not expose any governed packet")
    prep_library_event_controls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=event%20controls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_event_controls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_event_controls_path} returned {status}, expected 200")

    prep_library_event_controls = json.loads(body)
    if not (prep_library_event_controls.get("items") or []):
        raise AssertionError("prep-library event controls search did not expose any governed packet")
    prep_library_event_control_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=event-control"
    status, body, _, _ = fetch(
        base_url,
        prep_library_event_control_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_event_control_hyphen_path} returned {status}, expected 200")

    prep_library_event_control_hyphen = json.loads(body)
    if not (prep_library_event_control_hyphen.get("items") or []):
        raise AssertionError("prep-library event-control search did not expose any governed packet")
    prep_library_event_ctrl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=event%20ctrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_event_ctrl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_event_ctrl_path} returned {status}, expected 200")

    prep_library_event_ctrl = json.loads(body)
    if not (prep_library_event_ctrl.get("items") or []):
        raise AssertionError("prep-library event ctrl search did not expose any governed packet")
    prep_library_event_ctrl_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=event-ctrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_event_ctrl_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_event_ctrl_hyphen_path} returned {status}, expected 200")

    prep_library_event_ctrl_hyphen = json.loads(body)
    if not (prep_library_event_ctrl_hyphen.get("items") or []):
        raise AssertionError("prep-library event-ctrl search did not expose any governed packet")
    prep_library_eventctrl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=eventctrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_eventctrl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_eventctrl_path} returned {status}, expected 200")

    prep_library_eventctrl = json.loads(body)
    if not (prep_library_eventctrl.get("items") or []):
        raise AssertionError("prep-library eventctrl search did not expose any governed packet")
    prep_library_eventctl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=eventctl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_eventctl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_eventctl_path} returned {status}, expected 200")

    prep_library_eventctl = json.loads(body)
    if not (prep_library_eventctl.get("items") or []):
        raise AssertionError("prep-library eventctl search did not expose any governed packet")
    prep_library_eventctls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=eventctls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_eventctls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_eventctls_path} returned {status}, expected 200")

    prep_library_eventctls = json.loads(body)
    if not (prep_library_eventctls.get("items") or []):
        raise AssertionError("prep-library eventctls search did not expose any governed packet")
    prep_library_event_ctls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=event%20ctls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_event_ctls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_event_ctls_path} returned {status}, expected 200")

    prep_library_event_ctls = json.loads(body)
    if not (prep_library_event_ctls.get("items") or []):
        raise AssertionError("prep-library event ctls search did not expose any governed packet")
    prep_library_eventctrls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=eventctrls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_eventctrls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_eventctrls_path} returned {status}, expected 200")

    prep_library_eventctrls = json.loads(body)
    if not (prep_library_eventctrls.get("items") or []):
        raise AssertionError("prep-library eventctrls search did not expose any governed packet")
    prep_library_eventops_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=eventops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_eventops_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_eventops_path} returned {status}, expected 200")

    prep_library_eventops = json.loads(body)
    if not (prep_library_eventops.get("items") or []):
        raise AssertionError("prep-library eventops search did not expose any governed packet")
    prep_library_event_ops_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=event%20ops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_event_ops_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_event_ops_path} returned {status}, expected 200")

    prep_library_event_ops = json.loads(body)
    if not (prep_library_event_ops.get("items") or []):
        raise AssertionError("prep-library event ops search did not expose any governed packet")
    prep_library_eventop_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=eventop"
    status, body, _, _ = fetch(
        base_url,
        prep_library_eventop_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_eventop_path} returned {status}, expected 200")

    prep_library_eventop = json.loads(body)
    if not (prep_library_eventop.get("items") or []):
        raise AssertionError("prep-library eventop search did not expose any governed packet")
    prep_library_eventoperation_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=eventoperation"
    status, body, _, _ = fetch(
        base_url,
        prep_library_eventoperation_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_eventoperation_path} returned {status}, expected 200")

    prep_library_eventoperation = json.loads(body)
    if not (prep_library_eventoperation.get("items") or []):
        raise AssertionError("prep-library eventoperation search did not expose any governed packet")
    prep_library_eventoperations_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=eventoperations"
    status, body, _, _ = fetch(
        base_url,
        prep_library_eventoperations_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_eventoperations_path} returned {status}, expected 200")

    prep_library_eventoperations = json.loads(body)
    if not (prep_library_eventoperations.get("items") or []):
        raise AssertionError("prep-library eventoperations search did not expose any governed packet")
    prep_library_event_op_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=event-op"
    status, body, _, _ = fetch(
        base_url,
        prep_library_event_op_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_event_op_hyphen_path} returned {status}, expected 200")

    prep_library_event_op_hyphen = json.loads(body)
    if not (prep_library_event_op_hyphen.get("items") or []):
        raise AssertionError("prep-library event-op search did not expose any governed packet")
    prep_library_event_operation_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=event-operation"
    status, body, _, _ = fetch(
        base_url,
        prep_library_event_operation_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_event_operation_path} returned {status}, expected 200")

    prep_library_event_operation = json.loads(body)
    if not (prep_library_event_operation.get("items") or []):
        raise AssertionError("prep-library event-operation search did not expose any governed packet")
    prep_library_event_operations_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=event-operations"
    status, body, _, _ = fetch(
        base_url,
        prep_library_event_operations_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_event_operations_path} returned {status}, expected 200")

    prep_library_event_operations = json.loads(body)
    if not (prep_library_event_operations.get("items") or []):
        raise AssertionError("prep-library event-operations search did not expose any governed packet")
    prep_library_gmops_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gmops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gmops_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gmops_path} returned {status}, expected 200")

    prep_library_gmops = json.loads(body)
    if not (prep_library_gmops.get("items") or []):
        raise AssertionError("prep-library gmops search did not expose any governed packet")
    prep_library_gm_ops_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm%20ops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_ops_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_ops_path} returned {status}, expected 200")

    prep_library_gm_ops = json.loads(body)
    if not (prep_library_gm_ops.get("items") or []):
        raise AssertionError("prep-library gm ops search did not expose any governed packet")
    prep_library_gm_ops_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm-ops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_ops_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_ops_hyphen_path} returned {status}, expected 200")

    prep_library_gm_ops_hyphen = json.loads(body)
    if not (prep_library_gm_ops_hyphen.get("items") or []):
        raise AssertionError("prep-library gm-ops search did not expose any governed packet")
    prep_library_gmop_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gmop"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gmop_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gmop_path} returned {status}, expected 200")

    prep_library_gmop = json.loads(body)
    if not (prep_library_gmop.get("items") or []):
        raise AssertionError("prep-library gmop search did not expose any governed packet")
    prep_library_gm_op_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm-op"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_op_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_op_hyphen_path} returned {status}, expected 200")

    prep_library_gm_op_hyphen = json.loads(body)
    if not (prep_library_gm_op_hyphen.get("items") or []):
        raise AssertionError("prep-library gm-op search did not expose any governed packet")
    prep_library_gm_operation_compact_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gmoperation"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_operation_compact_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_operation_compact_path} returned {status}, expected 200")

    prep_library_gm_operation_compact = json.loads(body)
    if not (prep_library_gm_operation_compact.get("items") or []):
        raise AssertionError("prep-library gmoperation search did not expose any governed packet")
    prep_library_gm_operations_compact_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gmoperations"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_operations_compact_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_operations_compact_path} returned {status}, expected 200")

    prep_library_gm_operations_compact = json.loads(body)
    if not (prep_library_gm_operations_compact.get("items") or []):
        raise AssertionError("prep-library gmoperations search did not expose any governed packet")
    prep_library_gm_operation_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm%20operation"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_operation_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_operation_split_path} returned {status}, expected 200")

    prep_library_gm_operation_split = json.loads(body)
    if not (prep_library_gm_operation_split.get("items") or []):
        raise AssertionError("prep-library gm operation search did not expose any governed packet")
    prep_library_gm_operation_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm-operation"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_operation_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_operation_hyphen_path} returned {status}, expected 200")

    prep_library_gm_operation_hyphen = json.loads(body)
    if not (prep_library_gm_operation_hyphen.get("items") or []):
        raise AssertionError("prep-library gm-operation search did not expose any governed packet")
    prep_library_gm_operations_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm%20operations"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_operations_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_operations_split_path} returned {status}, expected 200")

    prep_library_gm_operations_split = json.loads(body)
    if not (prep_library_gm_operations_split.get("items") or []):
        raise AssertionError("prep-library gm operations search did not expose any governed packet")
    prep_library_gm_operations_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm-operations"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_operations_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_operations_hyphen_path} returned {status}, expected 200")

    prep_library_gm_operations_hyphen = json.loads(body)
    if not (prep_library_gm_operations_hyphen.get("items") or []):
        raise AssertionError("prep-library gm-operations search did not expose any governed packet")
    prep_library_gmcontrol_compact_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gmcontrol"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gmcontrol_compact_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gmcontrol_compact_path} returned {status}, expected 200")

    prep_library_gmcontrol_compact = json.loads(body)
    if not (prep_library_gmcontrol_compact.get("items") or []):
        raise AssertionError("prep-library gmcontrol search did not expose any governed packet")
    prep_library_gmcontrols_compact_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gmcontrols"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gmcontrols_compact_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gmcontrols_compact_path} returned {status}, expected 200")

    prep_library_gmcontrols_compact = json.loads(body)
    if not (prep_library_gmcontrols_compact.get("items") or []):
        raise AssertionError("prep-library gmcontrols search did not expose any governed packet")
    prep_library_gmctrl_compact_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gmctrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gmctrl_compact_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gmctrl_compact_path} returned {status}, expected 200")

    prep_library_gmctrl_compact = json.loads(body)
    if not (prep_library_gmctrl_compact.get("items") or []):
        raise AssertionError("prep-library gmctrl search did not expose any governed packet")
    prep_library_gmctrls_compact_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gmctrls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gmctrls_compact_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gmctrls_compact_path} returned {status}, expected 200")

    prep_library_gmctrls_compact = json.loads(body)
    if not (prep_library_gmctrls_compact.get("items") or []):
        raise AssertionError("prep-library gmctrls search did not expose any governed packet")
    prep_library_gmctl_compact_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gmctl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gmctl_compact_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gmctl_compact_path} returned {status}, expected 200")

    prep_library_gmctl_compact = json.loads(body)
    if not (prep_library_gmctl_compact.get("items") or []):
        raise AssertionError("prep-library gmctl search did not expose any governed packet")
    prep_library_gmctls_compact_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gmctls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gmctls_compact_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gmctls_compact_path} returned {status}, expected 200")

    prep_library_gmctls_compact = json.loads(body)
    if not (prep_library_gmctls_compact.get("items") or []):
        raise AssertionError("prep-library gmctls search did not expose any governed packet")
    prep_library_gm_ctls_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm-ctls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_ctls_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_ctls_hyphen_path} returned {status}, expected 200")

    prep_library_gm_ctls_hyphen = json.loads(body)
    if not (prep_library_gm_ctls_hyphen.get("items") or []):
        raise AssertionError("prep-library gm-ctls search did not expose any governed packet")
    prep_library_gm_ctls_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm%20ctls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_ctls_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_ctls_split_path} returned {status}, expected 200")

    prep_library_gm_ctls_split = json.loads(body)
    if not (prep_library_gm_ctls_split.get("items") or []):
        raise AssertionError("prep-library gm ctls search did not expose any governed packet")
    prep_library_gm_ctrls_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm%20ctrls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_ctrls_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_ctrls_split_path} returned {status}, expected 200")

    prep_library_gm_ctrls_split = json.loads(body)
    if not (prep_library_gm_ctrls_split.get("items") or []):
        raise AssertionError("prep-library gm ctrls search did not expose any governed packet")
    prep_library_gm_ctl_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm%20ctl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_ctl_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_ctl_split_path} returned {status}, expected 200")

    prep_library_gm_ctl_split = json.loads(body)
    if not (prep_library_gm_ctl_split.get("items") or []):
        raise AssertionError("prep-library gm ctl search did not expose any governed packet")
    prep_library_gm_ctl_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm-ctl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_ctl_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_ctl_hyphen_path} returned {status}, expected 200")

    prep_library_gm_ctl_hyphen = json.loads(body)
    if not (prep_library_gm_ctl_hyphen.get("items") or []):
        raise AssertionError("prep-library gm-ctl search did not expose any governed packet")
    prep_library_gm_control_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm%20control"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_control_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_control_split_path} returned {status}, expected 200")

    prep_library_gm_control_split = json.loads(body)
    if not (prep_library_gm_control_split.get("items") or []):
        raise AssertionError("prep-library gm control search did not expose any governed packet")
    prep_library_gm_control_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm-control"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_control_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_control_hyphen_path} returned {status}, expected 200")

    prep_library_gm_control_hyphen = json.loads(body)
    if not (prep_library_gm_control_hyphen.get("items") or []):
        raise AssertionError("prep-library gm-control search did not expose any governed packet")
    prep_library_gm_controls_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm%20controls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_controls_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_controls_split_path} returned {status}, expected 200")

    prep_library_gm_controls_split = json.loads(body)
    if not (prep_library_gm_controls_split.get("items") or []):
        raise AssertionError("prep-library gm controls search did not expose any governed packet")
    prep_library_gm_controls_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm-controls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_controls_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_controls_hyphen_path} returned {status}, expected 200")

    prep_library_gm_controls_hyphen = json.loads(body)
    if not (prep_library_gm_controls_hyphen.get("items") or []):
        raise AssertionError("prep-library gm-controls search did not expose any governed packet")
    prep_library_gm_ctrl_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm%20ctrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_ctrl_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_ctrl_split_path} returned {status}, expected 200")

    prep_library_gm_ctrl_split = json.loads(body)
    if not (prep_library_gm_ctrl_split.get("items") or []):
        raise AssertionError("prep-library gm ctrl search did not expose any governed packet")
    prep_library_gm_ctrl_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm-ctrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_ctrl_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_ctrl_hyphen_path} returned {status}, expected 200")

    prep_library_gm_ctrl_hyphen = json.loads(body)
    if not (prep_library_gm_ctrl_hyphen.get("items") or []):
        raise AssertionError("prep-library gm-ctrl search did not expose any governed packet")
    prep_library_gm_ctrls_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=gm-ctrls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_gm_ctrls_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_gm_ctrls_hyphen_path} returned {status}, expected 200")

    prep_library_gm_ctrls_hyphen = json.loads(body)
    if not (prep_library_gm_ctrls_hyphen.get("items") or []):
        raise AssertionError("prep-library gm-ctrls search did not expose any governed packet")
    prep_library_leagueops_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=leagueops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_leagueops_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_leagueops_path} returned {status}, expected 200")

    prep_library_leagueops = json.loads(body)
    if not (prep_library_leagueops.get("items") or []):
        raise AssertionError("prep-library leagueops search did not expose any governed packet")
    prep_library_leagueop_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=leagueop"
    status, body, _, _ = fetch(
        base_url,
        prep_library_leagueop_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_leagueop_path} returned {status}, expected 200")

    prep_library_leagueop = json.loads(body)
    if not (prep_library_leagueop.get("items") or []):
        raise AssertionError("prep-library leagueop search did not expose any governed packet")
    prep_library_leagueoperation_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=leagueoperation"
    status, body, _, _ = fetch(
        base_url,
        prep_library_leagueoperation_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_leagueoperation_path} returned {status}, expected 200")

    prep_library_leagueoperation = json.loads(body)
    if not (prep_library_leagueoperation.get("items") or []):
        raise AssertionError("prep-library leagueoperation search did not expose any governed packet")
    prep_library_league_op_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league-op"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_op_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_op_hyphen_path} returned {status}, expected 200")

    prep_library_league_op_hyphen = json.loads(body)
    if not (prep_library_league_op_hyphen.get("items") or []):
        raise AssertionError("prep-library league-op search did not expose any governed packet")
    prep_library_league_operation_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league-operation"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_operation_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_operation_hyphen_path} returned {status}, expected 200")

    prep_library_league_operation_hyphen = json.loads(body)
    if not (prep_library_league_operation_hyphen.get("items") or []):
        raise AssertionError("prep-library league-operation search did not expose any governed packet")
    prep_library_leagueoperations_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=leagueoperations"
    status, body, _, _ = fetch(
        base_url,
        prep_library_leagueoperations_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_leagueoperations_path} returned {status}, expected 200")

    prep_library_leagueoperations = json.loads(body)
    if not (prep_library_leagueoperations.get("items") or []):
        raise AssertionError("prep-library leagueoperations search did not expose any governed packet")
    prep_library_league_operations_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league-operations"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_operations_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_operations_hyphen_path} returned {status}, expected 200")

    prep_library_league_operations_hyphen = json.loads(body)
    if not (prep_library_league_operations_hyphen.get("items") or []):
        raise AssertionError("prep-library league-operations search did not expose any governed packet")
    prep_library_league_ops_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league%20ops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_ops_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_ops_path} returned {status}, expected 200")

    prep_library_league_ops = json.loads(body)
    if not (prep_library_league_ops.get("items") or []):
        raise AssertionError("prep-library league ops search did not expose any governed packet")
    prep_library_league_op_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league%20op"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_op_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_op_split_path} returned {status}, expected 200")

    prep_library_league_op_split = json.loads(body)
    if not (prep_library_league_op_split.get("items") or []):
        raise AssertionError("prep-library league op search did not expose any governed packet")
    prep_library_league_ops_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league-ops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_ops_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_ops_hyphen_path} returned {status}, expected 200")

    prep_library_league_ops_hyphen = json.loads(body)
    if not (prep_library_league_ops_hyphen.get("items") or []):
        raise AssertionError("prep-library league-ops search did not expose any governed packet")
    prep_library_leaguecontrol_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=leaguecontrol"
    status, body, _, _ = fetch(
        base_url,
        prep_library_leaguecontrol_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_leaguecontrol_path} returned {status}, expected 200")

    prep_library_leaguecontrol = json.loads(body)
    if not (prep_library_leaguecontrol.get("items") or []):
        raise AssertionError("prep-library leaguecontrol search did not expose any governed packet")
    prep_library_league_controls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league%20controls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_controls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_controls_path} returned {status}, expected 200")

    prep_library_league_controls = json.loads(body)
    if not (prep_library_league_controls.get("items") or []):
        raise AssertionError("prep-library league controls search did not expose any governed packet")
    prep_library_leaguecontrols_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=leaguecontrols"
    status, body, _, _ = fetch(
        base_url,
        prep_library_leaguecontrols_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_leaguecontrols_path} returned {status}, expected 200")

    prep_library_leaguecontrols = json.loads(body)
    if not (prep_library_leaguecontrols.get("items") or []):
        raise AssertionError("prep-library leaguecontrols search did not expose any governed packet")
    prep_library_league_control_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league%20control"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_control_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_control_path} returned {status}, expected 200")

    prep_library_league_control = json.loads(body)
    if not (prep_library_league_control.get("items") or []):
        raise AssertionError("prep-library league control search did not expose any governed packet")
    prep_library_league_control_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league-control"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_control_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_control_hyphen_path} returned {status}, expected 200")

    prep_library_league_control_hyphen = json.loads(body)
    if not (prep_library_league_control_hyphen.get("items") or []):
        raise AssertionError("prep-library league-control search did not expose any governed packet")
    prep_library_leaguectrl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=leaguectrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_leaguectrl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_leaguectrl_path} returned {status}, expected 200")

    prep_library_leaguectrl = json.loads(body)
    if not (prep_library_leaguectrl.get("items") or []):
        raise AssertionError("prep-library leaguectrl search did not expose any governed packet")
    prep_library_leaguectl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=leaguectl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_leaguectl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_leaguectl_path} returned {status}, expected 200")

    prep_library_leaguectl = json.loads(body)
    if not (prep_library_leaguectl.get("items") or []):
        raise AssertionError("prep-library leaguectl search did not expose any governed packet")
    prep_library_leaguectls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=leaguectls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_leaguectls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_leaguectls_path} returned {status}, expected 200")

    prep_library_leaguectls = json.loads(body)
    if not (prep_library_leaguectls.get("items") or []):
        raise AssertionError("prep-library leaguectls search did not expose any governed packet")
    prep_library_leaguectrls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=leaguectrls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_leaguectrls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_leaguectrls_path} returned {status}, expected 200")

    prep_library_leaguectrls = json.loads(body)
    if not (prep_library_leaguectrls.get("items") or []):
        raise AssertionError("prep-library leaguectrls search did not expose any governed packet")
    prep_library_league_ctl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league%20ctl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_ctl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_ctl_path} returned {status}, expected 200")

    prep_library_league_ctl = json.loads(body)
    if not (prep_library_league_ctl.get("items") or []):
        raise AssertionError("prep-library league ctl search did not expose any governed packet")
    prep_library_league_ctl_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league-ctl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_ctl_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_ctl_hyphen_path} returned {status}, expected 200")

    prep_library_league_ctl_hyphen = json.loads(body)
    if not (prep_library_league_ctl_hyphen.get("items") or []):
        raise AssertionError("prep-library league-ctl search did not expose any governed packet")
    prep_library_league_ctls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league%20ctls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_ctls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_ctls_path} returned {status}, expected 200")

    prep_library_league_ctls = json.loads(body)
    if not (prep_library_league_ctls.get("items") or []):
        raise AssertionError("prep-library league ctls search did not expose any governed packet")
    prep_library_league_ctls_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league-ctls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_ctls_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_ctls_hyphen_path} returned {status}, expected 200")

    prep_library_league_ctls_hyphen = json.loads(body)
    if not (prep_library_league_ctls_hyphen.get("items") or []):
        raise AssertionError("prep-library league-ctls search did not expose any governed packet")
    prep_library_league_ctrls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league%20ctrls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_ctrls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_ctrls_path} returned {status}, expected 200")

    prep_library_league_ctrls = json.loads(body)
    if not (prep_library_league_ctrls.get("items") or []):
        raise AssertionError("prep-library league ctrls search did not expose any governed packet")
    prep_library_league_ctrls_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league-ctrls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_ctrls_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_ctrls_hyphen_path} returned {status}, expected 200")

    prep_library_league_ctrls_hyphen = json.loads(body)
    if not (prep_library_league_ctrls_hyphen.get("items") or []):
        raise AssertionError("prep-library league-ctrls search did not expose any governed packet")
    prep_library_league_ctrl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league%20ctrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_ctrl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_ctrl_path} returned {status}, expected 200")

    prep_library_league_ctrl = json.loads(body)
    if not (prep_library_league_ctrl.get("items") or []):
        raise AssertionError("prep-library league ctrl search did not expose any governed packet")
    prep_library_league_ctrl_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=league-ctrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_league_ctrl_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_league_ctrl_hyphen_path} returned {status}, expected 200")

    prep_library_league_ctrl_hyphen = json.loads(body)
    if not (prep_library_league_ctrl_hyphen.get("items") or []):
        raise AssertionError("prep-library league-ctrl search did not expose any governed packet")
    prep_library_communityops_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=communityops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_communityops_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_communityops_path} returned {status}, expected 200")

    prep_library_communityops = json.loads(body)
    if not (prep_library_communityops.get("items") or []):
        raise AssertionError("prep-library communityops search did not expose any governed packet")
    prep_library_communityop_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=communityop"
    status, body, _, _ = fetch(
        base_url,
        prep_library_communityop_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_communityop_path} returned {status}, expected 200")

    prep_library_communityop = json.loads(body)
    if not (prep_library_communityop.get("items") or []):
        raise AssertionError("prep-library communityop search did not expose any governed packet")
    prep_library_communityoperation_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=communityoperation"
    status, body, _, _ = fetch(
        base_url,
        prep_library_communityoperation_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_communityoperation_path} returned {status}, expected 200")

    prep_library_communityoperation = json.loads(body)
    if not (prep_library_communityoperation.get("items") or []):
        raise AssertionError("prep-library communityoperation search did not expose any governed packet")
    prep_library_community_op_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community-op"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_op_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_op_hyphen_path} returned {status}, expected 200")

    prep_library_community_op_hyphen = json.loads(body)
    if not (prep_library_community_op_hyphen.get("items") or []):
        raise AssertionError("prep-library community-op search did not expose any governed packet")
    prep_library_community_operation_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community-operation"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_operation_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_operation_hyphen_path} returned {status}, expected 200")

    prep_library_community_operation_hyphen = json.loads(body)
    if not (prep_library_community_operation_hyphen.get("items") or []):
        raise AssertionError("prep-library community-operation search did not expose any governed packet")
    prep_library_communityoperations_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=communityoperations"
    status, body, _, _ = fetch(
        base_url,
        prep_library_communityoperations_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_communityoperations_path} returned {status}, expected 200")

    prep_library_communityoperations = json.loads(body)
    if not (prep_library_communityoperations.get("items") or []):
        raise AssertionError("prep-library communityoperations search did not expose any governed packet")
    prep_library_community_operations_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community-operations"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_operations_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_operations_hyphen_path} returned {status}, expected 200")

    prep_library_community_operations_hyphen = json.loads(body)
    if not (prep_library_community_operations_hyphen.get("items") or []):
        raise AssertionError("prep-library community-operations search did not expose any governed packet")
    prep_library_community_ops_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community%20ops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_ops_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_ops_path} returned {status}, expected 200")

    prep_library_community_ops = json.loads(body)
    if not (prep_library_community_ops.get("items") or []):
        raise AssertionError("prep-library community ops search did not expose any governed packet")
    prep_library_community_op_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community%20op"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_op_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_op_split_path} returned {status}, expected 200")

    prep_library_community_op_split = json.loads(body)
    if not (prep_library_community_op_split.get("items") or []):
        raise AssertionError("prep-library community op search did not expose any governed packet")
    prep_library_community_ops_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community-ops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_ops_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_ops_hyphen_path} returned {status}, expected 200")

    prep_library_community_ops_hyphen = json.loads(body)
    if not (prep_library_community_ops_hyphen.get("items") or []):
        raise AssertionError("prep-library community-ops search did not expose any governed packet")
    prep_library_communitycontrol_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=communitycontrol"
    status, body, _, _ = fetch(
        base_url,
        prep_library_communitycontrol_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_communitycontrol_path} returned {status}, expected 200")

    prep_library_communitycontrol = json.loads(body)
    if not (prep_library_communitycontrol.get("items") or []):
        raise AssertionError("prep-library communitycontrol search did not expose any governed packet")
    prep_library_community_controls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community%20controls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_controls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_controls_path} returned {status}, expected 200")

    prep_library_community_controls = json.loads(body)
    if not (prep_library_community_controls.get("items") or []):
        raise AssertionError("prep-library community controls search did not expose any governed packet")
    prep_library_communitycontrols_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=communitycontrols"
    status, body, _, _ = fetch(
        base_url,
        prep_library_communitycontrols_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_communitycontrols_path} returned {status}, expected 200")

    prep_library_communitycontrols = json.loads(body)
    if not (prep_library_communitycontrols.get("items") or []):
        raise AssertionError("prep-library communitycontrols search did not expose any governed packet")
    prep_library_community_control_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community%20control"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_control_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_control_path} returned {status}, expected 200")

    prep_library_community_control = json.loads(body)
    if not (prep_library_community_control.get("items") or []):
        raise AssertionError("prep-library community control search did not expose any governed packet")
    prep_library_community_control_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community-control"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_control_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_control_hyphen_path} returned {status}, expected 200")

    prep_library_community_control_hyphen = json.loads(body)
    if not (prep_library_community_control_hyphen.get("items") or []):
        raise AssertionError("prep-library community-control search did not expose any governed packet")
    prep_library_communityctrl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=communityctrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_communityctrl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_communityctrl_path} returned {status}, expected 200")

    prep_library_communityctrl = json.loads(body)
    if not (prep_library_communityctrl.get("items") or []):
        raise AssertionError("prep-library communityctrl search did not expose any governed packet")
    prep_library_communityctl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=communityctl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_communityctl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_communityctl_path} returned {status}, expected 200")

    prep_library_communityctl = json.loads(body)
    if not (prep_library_communityctl.get("items") or []):
        raise AssertionError("prep-library communityctl search did not expose any governed packet")
    prep_library_communityctls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=communityctls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_communityctls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_communityctls_path} returned {status}, expected 200")

    prep_library_communityctls = json.loads(body)
    if not (prep_library_communityctls.get("items") or []):
        raise AssertionError("prep-library communityctls search did not expose any governed packet")
    prep_library_communityctrls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=communityctrls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_communityctrls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_communityctrls_path} returned {status}, expected 200")

    prep_library_communityctrls = json.loads(body)
    if not (prep_library_communityctrls.get("items") or []):
        raise AssertionError("prep-library communityctrls search did not expose any governed packet")
    prep_library_community_ctl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community%20ctl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_ctl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_ctl_path} returned {status}, expected 200")

    prep_library_community_ctl = json.loads(body)
    if not (prep_library_community_ctl.get("items") or []):
        raise AssertionError("prep-library community ctl search did not expose any governed packet")
    prep_library_community_ctl_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community-ctl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_ctl_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_ctl_hyphen_path} returned {status}, expected 200")

    prep_library_community_ctl_hyphen = json.loads(body)
    if not (prep_library_community_ctl_hyphen.get("items") or []):
        raise AssertionError("prep-library community-ctl search did not expose any governed packet")
    prep_library_community_ctls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community%20ctls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_ctls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_ctls_path} returned {status}, expected 200")

    prep_library_community_ctls = json.loads(body)
    if not (prep_library_community_ctls.get("items") or []):
        raise AssertionError("prep-library community ctls search did not expose any governed packet")
    prep_library_community_ctls_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community-ctls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_ctls_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_ctls_hyphen_path} returned {status}, expected 200")

    prep_library_community_ctls_hyphen = json.loads(body)
    if not (prep_library_community_ctls_hyphen.get("items") or []):
        raise AssertionError("prep-library community-ctls search did not expose any governed packet")
    prep_library_community_ctrls_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community%20ctrls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_ctrls_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_ctrls_path} returned {status}, expected 200")

    prep_library_community_ctrls = json.loads(body)
    if not (prep_library_community_ctrls.get("items") or []):
        raise AssertionError("prep-library community ctrls search did not expose any governed packet")
    prep_library_community_ctrls_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community-ctrls"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_ctrls_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_ctrls_hyphen_path} returned {status}, expected 200")

    prep_library_community_ctrls_hyphen = json.loads(body)
    if not (prep_library_community_ctrls_hyphen.get("items") or []):
        raise AssertionError("prep-library community-ctrls search did not expose any governed packet")
    prep_library_community_ctrl_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community%20ctrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_ctrl_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_ctrl_path} returned {status}, expected 200")

    prep_library_community_ctrl = json.loads(body)
    if not (prep_library_community_ctrl.get("items") or []):
        raise AssertionError("prep-library community ctrl search did not expose any governed packet")
    prep_library_community_ctrl_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=community-ctrl"
    status, body, _, _ = fetch(
        base_url,
        prep_library_community_ctrl_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_community_ctrl_hyphen_path} returned {status}, expected 200")

    prep_library_community_ctrl_hyphen = json.loads(body)
    if not (prep_library_community_ctrl_hyphen.get("items") or []):
        raise AssertionError("prep-library community-ctrl search did not expose any governed packet")

    prep_library_heat_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=heat"
    status, body, _, _ = fetch(
        base_url,
        prep_library_heat_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_heat_path} returned {status}, expected 200")

    prep_library_heat = json.loads(body)
    if not (prep_library_heat.get("items") or []):
        raise AssertionError("prep-library heat search did not expose any governed packet")
    prep_library_heats_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=heats"
    status, body, _, _ = fetch(
        base_url,
        prep_library_heats_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_heats_path} returned {status}, expected 200")

    prep_library_heats = json.loads(body)
    if not (prep_library_heats.get("items") or []):
        raise AssertionError("prep-library heats search did not expose any governed packet")

    prep_library_contacts_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=contacts"
    status, body, _, _ = fetch(
        base_url,
        prep_library_contacts_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_contacts_path} returned {status}, expected 200")

    prep_library_contacts = json.loads(body)
    if not (prep_library_contacts.get("items") or []):
        raise AssertionError("prep-library contacts search did not expose any governed packet")
    prep_library_contact_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=contact"
    status, body, _, _ = fetch(
        base_url,
        prep_library_contact_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_contact_path} returned {status}, expected 200")

    prep_library_contact = json.loads(body)
    if not (prep_library_contact.get("items") or []):
        raise AssertionError("prep-library contact search did not expose any governed packet")
    prep_library_connection_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=connection"
    status, body, _, _ = fetch(
        base_url,
        prep_library_connection_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_connection_path} returned {status}, expected 200")

    prep_library_connection = json.loads(body)
    if not (prep_library_connection.get("items") or []):
        raise AssertionError("prep-library connection search did not expose any governed packet")
    prep_library_connections_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=connections"
    status, body, _, _ = fetch(
        base_url,
        prep_library_connections_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_connections_path} returned {status}, expected 200")

    prep_library_connections = json.loads(body)
    if not (prep_library_connections.get("items") or []):
        raise AssertionError("prep-library connections search did not expose any governed packet")
    prep_library_relationship_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=relationship"
    status, body, _, _ = fetch(
        base_url,
        prep_library_relationship_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_relationship_path} returned {status}, expected 200")

    prep_library_relationship = json.loads(body)
    if not (prep_library_relationship.get("items") or []):
        raise AssertionError("prep-library relationship search did not expose any governed packet")
    prep_library_relationships_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=relationships"
    status, body, _, _ = fetch(
        base_url,
        prep_library_relationships_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_relationships_path} returned {status}, expected 200")

    prep_library_relationships = json.loads(body)
    if not (prep_library_relationships.get("items") or []):
        raise AssertionError("prep-library relationships search did not expose any governed packet")
    prep_library_faction_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=faction"
    status, body, _, _ = fetch(
        base_url,
        prep_library_faction_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_faction_path} returned {status}, expected 200")

    prep_library_faction = json.loads(body)
    if not (prep_library_faction.get("items") or []):
        raise AssertionError("prep-library faction search did not expose any governed packet")
    prep_library_factions_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=factions"
    status, body, _, _ = fetch(
        base_url,
        prep_library_factions_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_factions_path} returned {status}, expected 200")

    prep_library_factions = json.loads(body)
    if not (prep_library_factions.get("items") or []):
        raise AssertionError("prep-library factions search did not expose any governed packet")
    prep_library_journal_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=journal"
    status, body, _, _ = fetch(
        base_url,
        prep_library_journal_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_journal_path} returned {status}, expected 200")

    prep_library_journal = json.loads(body)
    if not (prep_library_journal.get("items") or []):
        raise AssertionError("prep-library journal search did not expose any governed packet")
    prep_library_journals_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=journals"
    status, body, _, _ = fetch(
        base_url,
        prep_library_journals_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_journals_path} returned {status}, expected 200")

    prep_library_journals = json.loads(body)
    if not (prep_library_journals.get("items") or []):
        raise AssertionError("prep-library journals search did not expose any governed packet")
    prep_library_sessionlog_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=sessionlog"
    status, body, _, _ = fetch(
        base_url,
        prep_library_sessionlog_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_sessionlog_path} returned {status}, expected 200")

    prep_library_sessionlog = json.loads(body)
    if not (prep_library_sessionlog.get("items") or []):
        raise AssertionError("prep-library sessionlog search did not expose any governed packet")
    prep_library_sessionlogs_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=sessionlogs"
    status, body, _, _ = fetch(
        base_url,
        prep_library_sessionlogs_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_sessionlogs_path} returned {status}, expected 200")

    prep_library_sessionlogs = json.loads(body)
    if not (prep_library_sessionlogs.get("items") or []):
        raise AssertionError("prep-library sessionlogs search did not expose any governed packet")
    prep_library_session_logs_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=session%20logs"
    status, body, _, _ = fetch(
        base_url,
        prep_library_session_logs_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_session_logs_path} returned {status}, expected 200")

    prep_library_session_logs = json.loads(body)
    if not (prep_library_session_logs.get("items") or []):
        raise AssertionError("prep-library session logs search did not expose any governed packet")

    prep_library_diary_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=diary"
    status, body, _, _ = fetch(
        base_url,
        prep_library_diary_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_diary_path} returned {status}, expected 200")

    prep_library_diary = json.loads(body)
    if not (prep_library_diary.get("items") or []):
        raise AssertionError("prep-library diary search did not expose any governed packet")
    prep_library_diaries_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=diaries"
    status, body, _, _ = fetch(
        base_url,
        prep_library_diaries_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_diaries_path} returned {status}, expected 200")

    prep_library_diaries = json.loads(body)
    if not (prep_library_diaries.get("items") or []):
        raise AssertionError("prep-library diaries search did not expose any governed packet")

    prep_library_downtime_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=downtime"
    status, body, _, _ = fetch(
        base_url,
        prep_library_downtime_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_downtime_path} returned {status}, expected 200")

    prep_library_downtime = json.loads(body)
    if not (prep_library_downtime.get("items") or []):
        raise AssertionError("prep-library downtime search did not expose any governed packet")
    prep_library_downtimes_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=downtimes"
    status, body, _, _ = fetch(
        base_url,
        prep_library_downtimes_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_downtimes_path} returned {status}, expected 200")

    prep_library_downtimes = json.loads(body)
    if not (prep_library_downtimes.get("items") or []):
        raise AssertionError("prep-library downtimes search did not expose any governed packet")

    prep_library_aftermath_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=aftermath"
    status, body, _, _ = fetch(
        base_url,
        prep_library_aftermath_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_aftermath_path} returned {status}, expected 200")

    prep_library_aftermath = json.loads(body)
    if not (prep_library_aftermath.get("items") or []):
        raise AssertionError("prep-library aftermath search did not expose any governed packet")
    prep_library_aftermaths_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=aftermaths"
    status, body, _, _ = fetch(
        base_url,
        prep_library_aftermaths_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_aftermaths_path} returned {status}, expected 200")

    prep_library_aftermaths = json.loads(body)
    if not (prep_library_aftermaths.get("items") or []):
        raise AssertionError("prep-library aftermaths search did not expose any governed packet")
    prep_library_debrief_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=debrief"
    status, body, _, _ = fetch(
        base_url,
        prep_library_debrief_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_debrief_path} returned {status}, expected 200")

    prep_library_debrief = json.loads(body)
    if not (prep_library_debrief.get("items") or []):
        raise AssertionError("prep-library debrief search did not expose any governed packet")
    prep_library_debriefs_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=debriefs"
    status, body, _, _ = fetch(
        base_url,
        prep_library_debriefs_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_debriefs_path} returned {status}, expected 200")

    prep_library_debriefs = json.loads(body)
    if not (prep_library_debriefs.get("items") or []):
        raise AssertionError("prep-library debriefs search did not expose any governed packet")
    prep_library_debriefing_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=debriefing"
    status, body, _, _ = fetch(
        base_url,
        prep_library_debriefing_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_debriefing_path} returned {status}, expected 200")

    prep_library_debriefing = json.loads(body)
    if not (prep_library_debriefing.get("items") or []):
        raise AssertionError("prep-library debriefing search did not expose any governed packet")
    prep_library_debriefings_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=debriefings"
    status, body, _, _ = fetch(
        base_url,
        prep_library_debriefings_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_debriefings_path} returned {status}, expected 200")

    prep_library_debriefings = json.loads(body)
    if not (prep_library_debriefings.get("items") or []):
        raise AssertionError("prep-library debriefings search did not expose any governed packet")
    prep_library_postmortem_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=postmortem"
    status, body, _, _ = fetch(
        base_url,
        prep_library_postmortem_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_postmortem_path} returned {status}, expected 200")

    prep_library_postmortem = json.loads(body)
    if not (prep_library_postmortem.get("items") or []):
        raise AssertionError("prep-library postmortem search did not expose any governed packet")
    prep_library_post_mortem_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post%20mortem"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_mortem_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_mortem_path} returned {status}, expected 200")

    prep_library_post_mortem = json.loads(body)
    if not (prep_library_post_mortem.get("items") or []):
        raise AssertionError("prep-library post mortem search did not expose any governed packet")
    prep_library_post_mortem_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post-mortem"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_mortem_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_mortem_hyphen_path} returned {status}, expected 200")

    prep_library_post_mortem_hyphen = json.loads(body)
    if not (prep_library_post_mortem_hyphen.get("items") or []):
        raise AssertionError("prep-library post-mortem search did not expose any governed packet")
    prep_library_postmortems_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=postmortems"
    status, body, _, _ = fetch(
        base_url,
        prep_library_postmortems_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_postmortems_path} returned {status}, expected 200")

    prep_library_postmortems = json.loads(body)
    if not (prep_library_postmortems.get("items") or []):
        raise AssertionError("prep-library postmortems search did not expose any governed packet")
    prep_library_post_mortems_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post%20mortems"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_mortems_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_mortems_path} returned {status}, expected 200")

    prep_library_post_mortems = json.loads(body)
    if not (prep_library_post_mortems.get("items") or []):
        raise AssertionError("prep-library post mortems search did not expose any governed packet")
    prep_library_post_mortems_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post-mortems"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_mortems_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_mortems_hyphen_path} returned {status}, expected 200")

    prep_library_post_mortems_hyphen = json.loads(body)
    if not (prep_library_post_mortems_hyphen.get("items") or []):
        raise AssertionError("prep-library post-mortems search did not expose any governed packet")
    prep_library_postsession_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=postsession"
    status, body, _, _ = fetch(
        base_url,
        prep_library_postsession_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_postsession_path} returned {status}, expected 200")

    prep_library_postsession = json.loads(body)
    if not (prep_library_postsession.get("items") or []):
        raise AssertionError("prep-library postsession search did not expose any governed packet")
    prep_library_post_session_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post%20session"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_session_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_session_path} returned {status}, expected 200")

    prep_library_post_session = json.loads(body)
    if not (prep_library_post_session.get("items") or []):
        raise AssertionError("prep-library post session search did not expose any governed packet")
    prep_library_post_session_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post-session"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_session_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_session_hyphen_path} returned {status}, expected 200")

    prep_library_post_session_hyphen = json.loads(body)
    if not (prep_library_post_session_hyphen.get("items") or []):
        raise AssertionError("prep-library post-session search did not expose any governed packet")
    prep_library_postsessions_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=postsessions"
    status, body, _, _ = fetch(
        base_url,
        prep_library_postsessions_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_postsessions_path} returned {status}, expected 200")

    prep_library_postsessions = json.loads(body)
    if not (prep_library_postsessions.get("items") or []):
        raise AssertionError("prep-library postsessions search did not expose any governed packet")
    prep_library_post_sessions_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post%20sessions"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_sessions_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_sessions_path} returned {status}, expected 200")

    prep_library_post_sessions = json.loads(body)
    if not (prep_library_post_sessions.get("items") or []):
        raise AssertionError("prep-library post sessions search did not expose any governed packet")
    prep_library_post_sessions_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post-sessions"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_sessions_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_sessions_hyphen_path} returned {status}, expected 200")

    prep_library_post_sessions_hyphen = json.loads(body)
    if not (prep_library_post_sessions_hyphen.get("items") or []):
        raise AssertionError("prep-library post-sessions search did not expose any governed packet")
    prep_library_postrun_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=postrun"
    status, body, _, _ = fetch(
        base_url,
        prep_library_postrun_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_postrun_path} returned {status}, expected 200")

    prep_library_postrun = json.loads(body)
    if not (prep_library_postrun.get("items") or []):
        raise AssertionError("prep-library postrun search did not expose any governed packet")
    prep_library_post_run_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post%20run"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_run_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_run_path} returned {status}, expected 200")

    prep_library_post_run = json.loads(body)
    if not (prep_library_post_run.get("items") or []):
        raise AssertionError("prep-library post run search did not expose any governed packet")
    prep_library_post_run_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post-run"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_run_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_run_hyphen_path} returned {status}, expected 200")

    prep_library_post_run_hyphen = json.loads(body)
    if not (prep_library_post_run_hyphen.get("items") or []):
        raise AssertionError("prep-library post-run search did not expose any governed packet")
    prep_library_postruns_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=postruns"
    status, body, _, _ = fetch(
        base_url,
        prep_library_postruns_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_postruns_path} returned {status}, expected 200")

    prep_library_postruns = json.loads(body)
    if not (prep_library_postruns.get("items") or []):
        raise AssertionError("prep-library postruns search did not expose any governed packet")
    prep_library_post_runs_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post%20runs"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_runs_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_runs_path} returned {status}, expected 200")

    prep_library_post_runs = json.loads(body)
    if not (prep_library_post_runs.get("items") or []):
        raise AssertionError("prep-library post runs search did not expose any governed packet")
    prep_library_post_runs_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post-runs"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_runs_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_runs_hyphen_path} returned {status}, expected 200")

    prep_library_post_runs_hyphen = json.loads(body)
    if not (prep_library_post_runs_hyphen.get("items") or []):
        raise AssertionError("prep-library post-runs search did not expose any governed packet")
    prep_library_postgame_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=postgame"
    status, body, _, _ = fetch(
        base_url,
        prep_library_postgame_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_postgame_path} returned {status}, expected 200")

    prep_library_postgame = json.loads(body)
    if not (prep_library_postgame.get("items") or []):
        raise AssertionError("prep-library postgame search did not expose any governed packet")
    prep_library_postgames_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=postgames"
    status, body, _, _ = fetch(
        base_url,
        prep_library_postgames_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_postgames_path} returned {status}, expected 200")

    prep_library_postgames = json.loads(body)
    if not (prep_library_postgames.get("items") or []):
        raise AssertionError("prep-library postgames search did not expose any governed packet")
    prep_library_post_game_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post%20game"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_game_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_game_path} returned {status}, expected 200")

    prep_library_post_game = json.loads(body)
    if not (prep_library_post_game.get("items") or []):
        raise AssertionError("prep-library post game search did not expose any governed packet")
    prep_library_post_games_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post%20games"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_games_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_games_path} returned {status}, expected 200")

    prep_library_post_games = json.loads(body)
    if not (prep_library_post_games.get("items") or []):
        raise AssertionError("prep-library post games search did not expose any governed packet")
    prep_library_post_game_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post-game"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_game_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_game_hyphen_path} returned {status}, expected 200")

    prep_library_post_game_hyphen = json.loads(body)
    if not (prep_library_post_game_hyphen.get("items") or []):
        raise AssertionError("prep-library post-game search did not expose any governed packet")
    prep_library_post_games_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=post-games"
    status, body, _, _ = fetch(
        base_url,
        prep_library_post_games_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_post_games_hyphen_path} returned {status}, expected 200")

    prep_library_post_games_hyphen = json.loads(body)
    if not (prep_library_post_games_hyphen.get("items") or []):
        raise AssertionError("prep-library post-games search did not expose any governed packet")
    prep_library_recap_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=recap"
    status, body, _, _ = fetch(
        base_url,
        prep_library_recap_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_recap_path} returned {status}, expected 200")

    prep_library_recap = json.loads(body)
    if not (prep_library_recap.get("items") or []):
        raise AssertionError("prep-library recap search did not expose any governed packet")
    prep_library_recaps_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=recaps"
    status, body, _, _ = fetch(
        base_url,
        prep_library_recaps_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_recaps_path} returned {status}, expected 200")

    prep_library_recaps = json.loads(body)
    if not (prep_library_recaps.get("items") or []):
        raise AssertionError("prep-library recaps search did not expose any governed packet")
    prep_library_aar_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=aar"
    status, body, _, _ = fetch(
        base_url,
        prep_library_aar_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_aar_path} returned {status}, expected 200")

    prep_library_aar = json.loads(body)
    if not (prep_library_aar.get("items") or []):
        raise AssertionError("prep-library aar search did not expose any governed packet")
    prep_library_aars_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=aars"
    status, body, _, _ = fetch(
        base_url,
        prep_library_aars_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_aars_path} returned {status}, expected 200")

    prep_library_aars = json.loads(body)
    if not (prep_library_aars.get("items") or []):
        raise AssertionError("prep-library aars search did not expose any governed packet")
    prep_library_retro_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=retro"
    status, body, _, _ = fetch(
        base_url,
        prep_library_retro_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_retro_path} returned {status}, expected 200")

    prep_library_retro = json.loads(body)
    if not (prep_library_retro.get("items") or []):
        raise AssertionError("prep-library retro search did not expose any governed packet")
    prep_library_retros_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=retros"
    status, body, _, _ = fetch(
        base_url,
        prep_library_retros_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_retros_path} returned {status}, expected 200")

    prep_library_retros = json.loads(body)
    if not (prep_library_retros.get("items") or []):
        raise AssertionError("prep-library retros search did not expose any governed packet")
    prep_library_retrospective_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=retrospective"
    status, body, _, _ = fetch(
        base_url,
        prep_library_retrospective_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_retrospective_path} returned {status}, expected 200")

    prep_library_retrospective = json.loads(body)
    if not (prep_library_retrospective.get("items") or []):
        raise AssertionError("prep-library retrospective search did not expose any governed packet")
    prep_library_retrospectives_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=retrospectives"
    status, body, _, _ = fetch(
        base_url,
        prep_library_retrospectives_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_retrospectives_path} returned {status}, expected 200")

    prep_library_retrospectives = json.loads(body)
    if not (prep_library_retrospectives.get("items") or []):
        raise AssertionError("prep-library retrospectives search did not expose any governed packet")
    prep_library_hotwash_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=hotwash"
    status, body, _, _ = fetch(
        base_url,
        prep_library_hotwash_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_hotwash_path} returned {status}, expected 200")

    prep_library_hotwash = json.loads(body)
    if not (prep_library_hotwash.get("items") or []):
        raise AssertionError("prep-library hotwash search did not expose any governed packet")
    prep_library_hotwashes_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=hotwashes"
    status, body, _, _ = fetch(
        base_url,
        prep_library_hotwashes_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_hotwashes_path} returned {status}, expected 200")

    prep_library_hotwashes = json.loads(body)
    if not (prep_library_hotwashes.get("items") or []):
        raise AssertionError("prep-library hotwashes search did not expose any governed packet")
    prep_library_hot_wash_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=hot%20wash"
    status, body, _, _ = fetch(
        base_url,
        prep_library_hot_wash_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_hot_wash_path} returned {status}, expected 200")

    prep_library_hot_wash = json.loads(body)
    if not (prep_library_hot_wash.get("items") or []):
        raise AssertionError("prep-library hot wash search did not expose any governed packet")
    prep_library_hot_washes_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=hot%20washes"
    status, body, _, _ = fetch(
        base_url,
        prep_library_hot_washes_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_hot_washes_path} returned {status}, expected 200")

    prep_library_hot_washes = json.loads(body)
    if not (prep_library_hot_washes.get("items") or []):
        raise AssertionError("prep-library hot washes search did not expose any governed packet")
    prep_library_hot_wash_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=hot-wash"
    status, body, _, _ = fetch(
        base_url,
        prep_library_hot_wash_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_hot_wash_hyphen_path} returned {status}, expected 200")

    prep_library_hot_wash_hyphen = json.loads(body)
    if not (prep_library_hot_wash_hyphen.get("items") or []):
        raise AssertionError("prep-library hot-wash search did not expose any governed packet")
    prep_library_hot_washes_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=hot-washes"
    status, body, _, _ = fetch(
        base_url,
        prep_library_hot_washes_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_hot_washes_hyphen_path} returned {status}, expected 200")

    prep_library_hot_washes_hyphen = json.loads(body)
    if not (prep_library_hot_washes_hyphen.get("items") or []):
        raise AssertionError("prep-library hot-washes search did not expose any governed packet")
    prep_library_lesson_learned_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=lessonlearned"
    status, body, _, _ = fetch(
        base_url,
        prep_library_lesson_learned_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_lesson_learned_path} returned {status}, expected 200")

    prep_library_lesson_learned = json.loads(body)
    if not (prep_library_lesson_learned.get("items") or []):
        raise AssertionError("prep-library lessonlearned search did not expose any governed packet")
    prep_library_lessons_learned_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=lessonslearned"
    status, body, _, _ = fetch(
        base_url,
        prep_library_lessons_learned_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_lessons_learned_path} returned {status}, expected 200")

    prep_library_lessons_learned = json.loads(body)
    if not (prep_library_lessons_learned.get("items") or []):
        raise AssertionError("prep-library lessonslearned search did not expose any governed packet")
    prep_library_lesson_learnt_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=lessonlearnt"
    status, body, _, _ = fetch(
        base_url,
        prep_library_lesson_learnt_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_lesson_learnt_path} returned {status}, expected 200")

    prep_library_lesson_learnt = json.loads(body)
    if not (prep_library_lesson_learnt.get("items") or []):
        raise AssertionError("prep-library lessonlearnt search did not expose any governed packet")
    prep_library_lessons_learnt_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=lessonslearnt"
    status, body, _, _ = fetch(
        base_url,
        prep_library_lessons_learnt_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_lessons_learnt_path} returned {status}, expected 200")

    prep_library_lessons_learnt = json.loads(body)
    if not (prep_library_lessons_learnt.get("items") or []):
        raise AssertionError("prep-library lessonslearnt search did not expose any governed packet")
    prep_library_lesson_learned_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=lesson%20learned"
    status, body, _, _ = fetch(
        base_url,
        prep_library_lesson_learned_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_lesson_learned_split_path} returned {status}, expected 200")

    prep_library_lesson_learned_split = json.loads(body)
    if not (prep_library_lesson_learned_split.get("items") or []):
        raise AssertionError("prep-library lesson learned search did not expose any governed packet")
    prep_library_lessons_learned_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=lessons%20learned"
    status, body, _, _ = fetch(
        base_url,
        prep_library_lessons_learned_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_lessons_learned_split_path} returned {status}, expected 200")

    prep_library_lessons_learned_split = json.loads(body)
    if not (prep_library_lessons_learned_split.get("items") or []):
        raise AssertionError("prep-library lessons learned search did not expose any governed packet")
    prep_library_lesson_learnt_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=lesson%20learnt"
    status, body, _, _ = fetch(
        base_url,
        prep_library_lesson_learnt_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_lesson_learnt_split_path} returned {status}, expected 200")

    prep_library_lesson_learnt_split = json.loads(body)
    if not (prep_library_lesson_learnt_split.get("items") or []):
        raise AssertionError("prep-library lesson learnt search did not expose any governed packet")
    prep_library_lessons_learnt_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=lessons%20learnt"
    status, body, _, _ = fetch(
        base_url,
        prep_library_lessons_learnt_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_lessons_learnt_split_path} returned {status}, expected 200")

    prep_library_lessons_learnt_split = json.loads(body)
    if not (prep_library_lessons_learnt_split.get("items") or []):
        raise AssertionError("prep-library lessons learnt search did not expose any governed packet")
    prep_library_lesson_learnt_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=lesson-learnt"
    status, body, _, _ = fetch(
        base_url,
        prep_library_lesson_learnt_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_lesson_learnt_hyphen_path} returned {status}, expected 200")

    prep_library_lesson_learnt_hyphen = json.loads(body)
    if not (prep_library_lesson_learnt_hyphen.get("items") or []):
        raise AssertionError("prep-library lesson-learnt search did not expose any governed packet")
    prep_library_lessons_learnt_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=lessons-learnt"
    status, body, _, _ = fetch(
        base_url,
        prep_library_lessons_learnt_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_lessons_learnt_hyphen_path} returned {status}, expected 200")

    prep_library_lessons_learnt_hyphen = json.loads(body)
    if not (prep_library_lessons_learnt_hyphen.get("items") or []):
        raise AssertionError("prep-library lessons-learnt search did not expose any governed packet")
    prep_library_lesson_learned_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=lesson-learned"
    status, body, _, _ = fetch(
        base_url,
        prep_library_lesson_learned_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_lesson_learned_hyphen_path} returned {status}, expected 200")

    prep_library_lesson_learned_hyphen = json.loads(body)
    if not (prep_library_lesson_learned_hyphen.get("items") or []):
        raise AssertionError("prep-library lesson-learned search did not expose any governed packet")
    prep_library_lessons_learned_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=lessons-learned"
    status, body, _, _ = fetch(
        base_url,
        prep_library_lessons_learned_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_lessons_learned_hyphen_path} returned {status}, expected 200")

    prep_library_lessons_learned_hyphen = json.loads(body)
    if not (prep_library_lessons_learned_hyphen.get("items") or []):
        raise AssertionError("prep-library lessons-learned search did not expose any governed packet")
    prep_library_afteraction_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=afteraction"
    status, body, _, _ = fetch(
        base_url,
        prep_library_afteraction_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_afteraction_path} returned {status}, expected 200")

    prep_library_afteraction = json.loads(body)
    if not (prep_library_afteraction.get("items") or []):
        raise AssertionError("prep-library afteraction search did not expose any governed packet")
    prep_library_afteractions_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=afteractions"
    status, body, _, _ = fetch(
        base_url,
        prep_library_afteractions_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_afteractions_path} returned {status}, expected 200")

    prep_library_afteractions = json.loads(body)
    if not (prep_library_afteractions.get("items") or []):
        raise AssertionError("prep-library afteractions search did not expose any governed packet")
    prep_library_afteractionreport_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=afteractionreport"
    status, body, _, _ = fetch(
        base_url,
        prep_library_afteractionreport_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_afteractionreport_path} returned {status}, expected 200")

    prep_library_afteractionreport = json.loads(body)
    if not (prep_library_afteractionreport.get("items") or []):
        raise AssertionError("prep-library afteractionreport search did not expose any governed packet")
    prep_library_afteractionreports_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=afteractionreports"
    status, body, _, _ = fetch(
        base_url,
        prep_library_afteractionreports_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_afteractionreports_path} returned {status}, expected 200")

    prep_library_afteractionreports = json.loads(body)
    if not (prep_library_afteractionreports.get("items") or []):
        raise AssertionError("prep-library afteractionreports search did not expose any governed packet")
    prep_library_afteractionreview_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=afteractionreview"
    status, body, _, _ = fetch(
        base_url,
        prep_library_afteractionreview_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_afteractionreview_path} returned {status}, expected 200")

    prep_library_afteractionreview = json.loads(body)
    if not (prep_library_afteractionreview.get("items") or []):
        raise AssertionError("prep-library afteractionreview search did not expose any governed packet")
    prep_library_afteractionreviews_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=afteractionreviews"
    status, body, _, _ = fetch(
        base_url,
        prep_library_afteractionreviews_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_afteractionreviews_path} returned {status}, expected 200")

    prep_library_afteractionreviews = json.loads(body)
    if not (prep_library_afteractionreviews.get("items") or []):
        raise AssertionError("prep-library afteractionreviews search did not expose any governed packet")
    prep_library_after_action_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=after%20action"
    status, body, _, _ = fetch(
        base_url,
        prep_library_after_action_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_after_action_path} returned {status}, expected 200")

    prep_library_after_action = json.loads(body)
    if not (prep_library_after_action.get("items") or []):
        raise AssertionError("prep-library after action search did not expose any governed packet")
    prep_library_after_actions_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=after%20actions"
    status, body, _, _ = fetch(
        base_url,
        prep_library_after_actions_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_after_actions_path} returned {status}, expected 200")

    prep_library_after_actions = json.loads(body)
    if not (prep_library_after_actions.get("items") or []):
        raise AssertionError("prep-library after actions search did not expose any governed packet")
    prep_library_after_action_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=after-action"
    status, body, _, _ = fetch(
        base_url,
        prep_library_after_action_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_after_action_hyphen_path} returned {status}, expected 200")

    prep_library_after_action_hyphen = json.loads(body)
    if not (prep_library_after_action_hyphen.get("items") or []):
        raise AssertionError("prep-library after-action search did not expose any governed packet")
    prep_library_after_actions_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=after-actions"
    status, body, _, _ = fetch(
        base_url,
        prep_library_after_actions_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_after_actions_hyphen_path} returned {status}, expected 200")

    prep_library_after_actions_hyphen = json.loads(body)
    if not (prep_library_after_actions_hyphen.get("items") or []):
        raise AssertionError("prep-library after-actions search did not expose any governed packet")
    prep_library_after_action_report_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=after%20action%20report"
    status, body, _, _ = fetch(
        base_url,
        prep_library_after_action_report_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_after_action_report_path} returned {status}, expected 200")

    prep_library_after_action_report = json.loads(body)
    if not (prep_library_after_action_report.get("items") or []):
        raise AssertionError("prep-library after action report search did not expose any governed packet")
    prep_library_after_action_reports_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=after%20action%20reports"
    status, body, _, _ = fetch(
        base_url,
        prep_library_after_action_reports_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_after_action_reports_path} returned {status}, expected 200")

    prep_library_after_action_reports = json.loads(body)
    if not (prep_library_after_action_reports.get("items") or []):
        raise AssertionError("prep-library after action reports search did not expose any governed packet")
    prep_library_after_action_review_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=after%20action%20review"
    status, body, _, _ = fetch(
        base_url,
        prep_library_after_action_review_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_after_action_review_path} returned {status}, expected 200")

    prep_library_after_action_review = json.loads(body)
    if not (prep_library_after_action_review.get("items") or []):
        raise AssertionError("prep-library after action review search did not expose any governed packet")
    prep_library_after_action_reviews_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=after%20action%20reviews"
    status, body, _, _ = fetch(
        base_url,
        prep_library_after_action_reviews_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_after_action_reviews_path} returned {status}, expected 200")

    prep_library_after_action_reviews = json.loads(body)
    if not (prep_library_after_action_reviews.get("items") or []):
        raise AssertionError("prep-library after action reviews search did not expose any governed packet")
    prep_library_after_action_report_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=after-action%20report"
    status, body, _, _ = fetch(
        base_url,
        prep_library_after_action_report_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_after_action_report_hyphen_path} returned {status}, expected 200")

    prep_library_after_action_report_hyphen = json.loads(body)
    if not (prep_library_after_action_report_hyphen.get("items") or []):
        raise AssertionError("prep-library after-action report search did not expose any governed packet")
    prep_library_after_action_reports_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=after-action%20reports"
    status, body, _, _ = fetch(
        base_url,
        prep_library_after_action_reports_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_after_action_reports_hyphen_path} returned {status}, expected 200")

    prep_library_after_action_reports_hyphen = json.loads(body)
    if not (prep_library_after_action_reports_hyphen.get("items") or []):
        raise AssertionError("prep-library after-action reports search did not expose any governed packet")
    prep_library_after_action_review_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=after-action%20review"
    status, body, _, _ = fetch(
        base_url,
        prep_library_after_action_review_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_after_action_review_hyphen_path} returned {status}, expected 200")

    prep_library_after_action_review_hyphen = json.loads(body)
    if not (prep_library_after_action_review_hyphen.get("items") or []):
        raise AssertionError("prep-library after-action review search did not expose any governed packet")
    prep_library_after_action_reviews_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=after-action%20reviews"
    status, body, _, _ = fetch(
        base_url,
        prep_library_after_action_reviews_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_after_action_reviews_hyphen_path} returned {status}, expected 200")

    prep_library_after_action_reviews_hyphen = json.loads(body)
    if not (prep_library_after_action_reviews_hyphen.get("items") or []):
        raise AssertionError("prep-library after-action reviews search did not expose any governed packet")

    prep_library_return_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=return"
    status, body, _, _ = fetch(
        base_url,
        prep_library_return_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_return_path} returned {status}, expected 200")

    prep_library_return = json.loads(body)
    if not (prep_library_return.get("items") or []):
        raise AssertionError("prep-library return search did not expose any governed packet")
    prep_library_returns_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=returns"
    status, body, _, _ = fetch(
        base_url,
        prep_library_returns_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_returns_path} returned {status}, expected 200")

    prep_library_returns = json.loads(body)
    if not (prep_library_returns.get("items") or []):
        raise AssertionError("prep-library returns search did not expose any governed packet")
    prep_library_return_loop_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=returnloop"
    status, body, _, _ = fetch(
        base_url,
        prep_library_return_loop_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_return_loop_path} returned {status}, expected 200")

    prep_library_return_loop = json.loads(body)
    if not (prep_library_return_loop.get("items") or []):
        raise AssertionError("prep-library returnloop search did not expose any governed packet")
    prep_library_return_loops_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=returnloops"
    status, body, _, _ = fetch(
        base_url,
        prep_library_return_loops_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_return_loops_path} returned {status}, expected 200")

    prep_library_return_loops = json.loads(body)
    if not (prep_library_return_loops.get("items") or []):
        raise AssertionError("prep-library returnloops search did not expose any governed packet")
    prep_library_next_session_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=nextsession"
    status, body, _, _ = fetch(
        base_url,
        prep_library_next_session_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_next_session_path} returned {status}, expected 200")

    prep_library_next_session = json.loads(body)
    if not (prep_library_next_session.get("items") or []):
        raise AssertionError("prep-library nextsession search did not expose any governed packet")
    prep_library_next_sessions_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=nextsessions"
    status, body, _, _ = fetch(
        base_url,
        prep_library_next_sessions_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_next_sessions_path} returned {status}, expected 200")

    prep_library_next_sessions = json.loads(body)
    if not (prep_library_next_sessions.get("items") or []):
        raise AssertionError("prep-library nextsessions search did not expose any governed packet")
    prep_library_next_session_return_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=nextsessionreturn"
    status, body, _, _ = fetch(
        base_url,
        prep_library_next_session_return_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_next_session_return_path} returned {status}, expected 200")

    prep_library_next_session_return = json.loads(body)
    if not (prep_library_next_session_return.get("items") or []):
        raise AssertionError("prep-library nextsessionreturn search did not expose any governed packet")
    prep_library_next_session_returns_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=nextsessionreturns"
    status, body, _, _ = fetch(
        base_url,
        prep_library_next_session_returns_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_next_session_returns_path} returned {status}, expected 200")

    prep_library_next_session_returns = json.loads(body)
    if not (prep_library_next_session_returns.get("items") or []):
        raise AssertionError("prep-library nextsessionreturns search did not expose any governed packet")
    prep_library_session_return_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=sessionreturn"
    status, body, _, _ = fetch(
        base_url,
        prep_library_session_return_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_session_return_path} returned {status}, expected 200")

    prep_library_session_return = json.loads(body)
    if not (prep_library_session_return.get("items") or []):
        raise AssertionError("prep-library sessionreturn search did not expose any governed packet")
    prep_library_session_returns_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=sessionreturns"
    status, body, _, _ = fetch(
        base_url,
        prep_library_session_returns_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_session_returns_path} returned {status}, expected 200")

    prep_library_session_returns = json.loads(body)
    if not (prep_library_session_returns.get("items") or []):
        raise AssertionError("prep-library sessionreturns search did not expose any governed packet")
    prep_library_memory_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=memory"
    status, body, _, _ = fetch(
        base_url,
        prep_library_memory_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_memory_path} returned {status}, expected 200")

    prep_library_memory = json.loads(body)
    if not (prep_library_memory.get("items") or []):
        raise AssertionError("prep-library memory search did not expose any governed packet")
    prep_library_memories_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=memories"
    status, body, _, _ = fetch(
        base_url,
        prep_library_memories_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_memories_path} returned {status}, expected 200")

    prep_library_memories = json.loads(body)
    if not (prep_library_memories.get("items") or []):
        raise AssertionError("prep-library memories search did not expose any governed packet")
    prep_library_archive_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=archive"
    status, body, _, _ = fetch(
        base_url,
        prep_library_archive_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_archive_path} returned {status}, expected 200")

    prep_library_archive = json.loads(body)
    if not (prep_library_archive.get("items") or []):
        raise AssertionError("prep-library archive search did not expose any governed packet")
    prep_library_archives_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=archives"
    status, body, _, _ = fetch(
        base_url,
        prep_library_archives_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_archives_path} returned {status}, expected 200")

    prep_library_archives = json.loads(body)
    if not (prep_library_archives.get("items") or []):
        raise AssertionError("prep-library archives search did not expose any governed packet")
    prep_library_history_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=history"
    status, body, _, _ = fetch(
        base_url,
        prep_library_history_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_history_path} returned {status}, expected 200")

    prep_library_history = json.loads(body)
    if not (prep_library_history.get("items") or []):
        raise AssertionError("prep-library history search did not expose any governed packet")
    prep_library_histories_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=histories"
    status, body, _, _ = fetch(
        base_url,
        prep_library_histories_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_histories_path} returned {status}, expected 200")

    prep_library_histories = json.loads(body)
    if not (prep_library_histories.get("items") or []):
        raise AssertionError("prep-library histories search did not expose any governed packet")
    prep_library_timeline_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=timeline"
    status, body, _, _ = fetch(
        base_url,
        prep_library_timeline_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_timeline_path} returned {status}, expected 200")

    prep_library_timeline = json.loads(body)
    if not (prep_library_timeline.get("items") or []):
        raise AssertionError("prep-library timeline search did not expose any governed packet")
    prep_library_timelines_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=timelines"
    status, body, _, _ = fetch(
        base_url,
        prep_library_timelines_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_timelines_path} returned {status}, expected 200")

    prep_library_timelines = json.loads(body)
    if not (prep_library_timelines.get("items") or []):
        raise AssertionError("prep-library timelines search did not expose any governed packet")
    prep_library_ledger_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=ledger"
    status, body, _, _ = fetch(
        base_url,
        prep_library_ledger_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_ledger_path} returned {status}, expected 200")

    prep_library_ledger = json.loads(body)
    if not (prep_library_ledger.get("items") or []):
        raise AssertionError("prep-library ledger search did not expose any governed packet")
    prep_library_ledgers_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=ledgers"
    status, body, _, _ = fetch(
        base_url,
        prep_library_ledgers_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_ledgers_path} returned {status}, expected 200")

    prep_library_ledgers = json.loads(body)
    if not (prep_library_ledgers.get("items") or []):
        raise AssertionError("prep-library ledgers search did not expose any governed packet")

    prep_library_roster_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=roster"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_path} returned {status}, expected 200")

    prep_library_roster = json.loads(body)
    if not (prep_library_roster.get("items") or []):
        raise AssertionError("prep-library roster search did not expose any governed packet")
    prep_library_roster_move_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=rostermove"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_move_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_move_path} returned {status}, expected 200")

    prep_library_roster_move = json.loads(body)
    if not (prep_library_roster_move.get("items") or []):
        raise AssertionError("prep-library rostermove search did not expose any governed packet")
    prep_library_crew_move_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crewmove"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_move_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_move_path} returned {status}, expected 200")

    prep_library_crew_move = json.loads(body)
    if not (prep_library_crew_move.get("items") or []):
        raise AssertionError("prep-library crewmove search did not expose any governed packet")
    prep_library_crew_moves_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crewmoves"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_moves_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_moves_path} returned {status}, expected 200")

    prep_library_crew_moves = json.loads(body)
    if not (prep_library_crew_moves.get("items") or []):
        raise AssertionError("prep-library crewmoves search did not expose any governed packet")
    prep_library_crew_swap_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crewswap"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_swap_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_swap_path} returned {status}, expected 200")

    prep_library_crew_swap = json.loads(body)
    if not (prep_library_crew_swap.get("items") or []):
        raise AssertionError("prep-library crewswap search did not expose any governed packet")
    prep_library_crew_swaps_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crewswaps"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_swaps_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_swaps_path} returned {status}, expected 200")

    prep_library_crew_swaps = json.loads(body)
    if not (prep_library_crew_swaps.get("items") or []):
        raise AssertionError("prep-library crewswaps search did not expose any governed packet")
    prep_library_roster_moves_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=rostermoves"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_moves_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_moves_path} returned {status}, expected 200")

    prep_library_roster_moves = json.loads(body)
    if not (prep_library_roster_moves.get("items") or []):
        raise AssertionError("prep-library rostermoves search did not expose any governed packet")
    prep_library_roster_swap_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=rosterswap"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_swap_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_swap_path} returned {status}, expected 200")

    prep_library_roster_swap = json.loads(body)
    if not (prep_library_roster_swap.get("items") or []):
        raise AssertionError("prep-library rosterswap search did not expose any governed packet")
    prep_library_roster_swaps_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=rosterswaps"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_swaps_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_swaps_path} returned {status}, expected 200")

    prep_library_roster_swaps = json.loads(body)
    if not (prep_library_roster_swaps.get("items") or []):
        raise AssertionError("prep-library rosterswaps search did not expose any governed packet")
    prep_library_roster_transfer_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=rostertransfer"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_transfer_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_transfer_path} returned {status}, expected 200")

    prep_library_roster_transfer = json.loads(body)
    if not (prep_library_roster_transfer.get("items") or []):
        raise AssertionError("prep-library rostertransfer search did not expose any governed packet")
    prep_library_roster_transfers_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=rostertransfers"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_transfers_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_transfers_path} returned {status}, expected 200")

    prep_library_roster_transfers = json.loads(body)
    if not (prep_library_roster_transfers.get("items") or []):
        raise AssertionError("prep-library rostertransfers search did not expose any governed packet")
    prep_library_roster_handoff_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=rosterhandoff"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_handoff_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_handoff_path} returned {status}, expected 200")

    prep_library_roster_handoff = json.loads(body)
    if not (prep_library_roster_handoff.get("items") or []):
        raise AssertionError("prep-library rosterhandoff search did not expose any governed packet")
    prep_library_roster_handoffs_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=rosterhandoffs"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_handoffs_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_handoffs_path} returned {status}, expected 200")

    prep_library_roster_handoffs = json.loads(body)
    if not (prep_library_roster_handoffs.get("items") or []):
        raise AssertionError("prep-library rosterhandoffs search did not expose any governed packet")
    prep_library_crew_handoff_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crewhandoff"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_handoff_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_handoff_path} returned {status}, expected 200")

    prep_library_crew_handoff = json.loads(body)
    if not (prep_library_crew_handoff.get("items") or []):
        raise AssertionError("prep-library crewhandoff search did not expose any governed packet")
    prep_library_crew_handoffs_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crewhandoffs"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_handoffs_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_handoffs_path} returned {status}, expected 200")

    prep_library_crew_handoffs = json.loads(body)
    if not (prep_library_crew_handoffs.get("items") or []):
        raise AssertionError("prep-library crewhandoffs search did not expose any governed packet")
    prep_library_crew_transfer_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crewtransfer"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_transfer_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_transfer_path} returned {status}, expected 200")

    prep_library_crew_transfer = json.loads(body)
    if not (prep_library_crew_transfer.get("items") or []):
        raise AssertionError("prep-library crewtransfer search did not expose any governed packet")
    prep_library_crew_transfers_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crewtransfers"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_transfers_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_transfers_path} returned {status}, expected 200")

    prep_library_crew_transfers = json.loads(body)
    if not (prep_library_crew_transfers.get("items") or []):
        raise AssertionError("prep-library crewtransfers search did not expose any governed packet")
    prep_library_crew_transfers_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crew%20transfers"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_transfers_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_transfers_split_path} returned {status}, expected 200")

    prep_library_crew_transfers_split = json.loads(body)
    if not (prep_library_crew_transfers_split.get("items") or []):
        raise AssertionError("prep-library crew transfers search did not expose any governed packet")
    prep_library_crew_transfer_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crew%20transfer"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_transfer_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_transfer_split_path} returned {status}, expected 200")

    prep_library_crew_transfer_split = json.loads(body)
    if not (prep_library_crew_transfer_split.get("items") or []):
        raise AssertionError("prep-library crew transfer search did not expose any governed packet")
    prep_library_crew_handoffs_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crew%20handoffs"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_handoffs_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_handoffs_split_path} returned {status}, expected 200")

    prep_library_crew_handoffs_split = json.loads(body)
    if not (prep_library_crew_handoffs_split.get("items") or []):
        raise AssertionError("prep-library crew handoffs search did not expose any governed packet")
    prep_library_crew_handoff_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crew%20handoff"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_handoff_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_handoff_split_path} returned {status}, expected 200")

    prep_library_crew_handoff_split = json.loads(body)
    if not (prep_library_crew_handoff_split.get("items") or []):
        raise AssertionError("prep-library crew handoff search did not expose any governed packet")
    prep_library_crew_moves_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crew%20moves"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_moves_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_moves_split_path} returned {status}, expected 200")

    prep_library_crew_moves_split = json.loads(body)
    if not (prep_library_crew_moves_split.get("items") or []):
        raise AssertionError("prep-library crew moves search did not expose any governed packet")
    prep_library_crew_move_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crew%20move"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_move_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_move_split_path} returned {status}, expected 200")

    prep_library_crew_move_split = json.loads(body)
    if not (prep_library_crew_move_split.get("items") or []):
        raise AssertionError("prep-library crew move search did not expose any governed packet")
    prep_library_roster_transfers_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=roster%20transfers"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_transfers_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_transfers_split_path} returned {status}, expected 200")

    prep_library_roster_transfers_split = json.loads(body)
    if not (prep_library_roster_transfers_split.get("items") or []):
        raise AssertionError("prep-library roster transfers search did not expose any governed packet")
    prep_library_roster_transfer_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=roster%20transfer"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_transfer_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_transfer_split_path} returned {status}, expected 200")

    prep_library_roster_transfer_split = json.loads(body)
    if not (prep_library_roster_transfer_split.get("items") or []):
        raise AssertionError("prep-library roster transfer search did not expose any governed packet")
    prep_library_roster_handoffs_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=roster%20handoffs"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_handoffs_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_handoffs_split_path} returned {status}, expected 200")

    prep_library_roster_handoffs_split = json.loads(body)
    if not (prep_library_roster_handoffs_split.get("items") or []):
        raise AssertionError("prep-library roster handoffs search did not expose any governed packet")
    prep_library_roster_handoff_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=roster%20handoff"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_handoff_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_handoff_split_path} returned {status}, expected 200")

    prep_library_roster_handoff_split = json.loads(body)
    if not (prep_library_roster_handoff_split.get("items") or []):
        raise AssertionError("prep-library roster handoff search did not expose any governed packet")
    prep_library_roster_moves_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=roster%20moves"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_moves_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_moves_split_path} returned {status}, expected 200")

    prep_library_roster_moves_split = json.loads(body)
    if not (prep_library_roster_moves_split.get("items") or []):
        raise AssertionError("prep-library roster moves search did not expose any governed packet")
    prep_library_roster_move_split_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=roster%20move"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_move_split_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_move_split_path} returned {status}, expected 200")

    prep_library_roster_move_split = json.loads(body)
    if not (prep_library_roster_move_split.get("items") or []):
        raise AssertionError("prep-library roster move search did not expose any governed packet")
    prep_library_roster_move_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=roster-move"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_move_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_move_hyphen_path} returned {status}, expected 200")

    prep_library_roster_move_hyphen = json.loads(body)
    if not (prep_library_roster_move_hyphen.get("items") or []):
        raise AssertionError("prep-library roster-move search did not expose any governed packet")
    prep_library_crew_move_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crew-move"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_move_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_move_hyphen_path} returned {status}, expected 200")

    prep_library_crew_move_hyphen = json.loads(body)
    if not (prep_library_crew_move_hyphen.get("items") or []):
        raise AssertionError("prep-library crew-move search did not expose any governed packet")
    prep_library_roster_transfer_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=roster-transfer"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_transfer_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_transfer_hyphen_path} returned {status}, expected 200")

    prep_library_roster_transfer_hyphen = json.loads(body)
    if not (prep_library_roster_transfer_hyphen.get("items") or []):
        raise AssertionError("prep-library roster-transfer search did not expose any governed packet")
    prep_library_crew_transfer_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crew-transfer"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_transfer_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_transfer_hyphen_path} returned {status}, expected 200")

    prep_library_crew_transfer_hyphen = json.loads(body)
    if not (prep_library_crew_transfer_hyphen.get("items") or []):
        raise AssertionError("prep-library crew-transfer search did not expose any governed packet")
    prep_library_roster_handoff_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=roster-handoff"
    status, body, _, _ = fetch(
        base_url,
        prep_library_roster_handoff_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_roster_handoff_hyphen_path} returned {status}, expected 200")

    prep_library_roster_handoff_hyphen = json.loads(body)
    if not (prep_library_roster_handoff_hyphen.get("items") or []):
        raise AssertionError("prep-library roster-handoff search did not expose any governed packet")
    prep_library_crew_handoff_hyphen_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=crew-handoff"
    status, body, _, _ = fetch(
        base_url,
        prep_library_crew_handoff_hyphen_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_crew_handoff_hyphen_path} returned {status}, expected 200")

    prep_library_crew_handoff_hyphen = json.loads(body)
    if not (prep_library_crew_handoff_hyphen.get("items") or []):
        raise AssertionError("prep-library crew-handoff search did not expose any governed packet")
    prep_library_preplaunch_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=preplaunch"
    status, body, _, _ = fetch(
        base_url,
        prep_library_preplaunch_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_preplaunch_path} returned {status}, expected 200")

    prep_library_preplaunch = json.loads(body)
    if not (prep_library_preplaunch.get("items") or []):
        raise AssertionError("prep-library preplaunch search did not expose any governed packet")
    prep_library_preplaunches_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=preplaunches"
    status, body, _, _ = fetch(
        base_url,
        prep_library_preplaunches_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_preplaunches_path} returned {status}, expected 200")

    prep_library_preplaunches = json.loads(body)
    if not (prep_library_preplaunches.get("items") or []):
        raise AssertionError("prep-library preplaunches search did not expose any governed packet")
    prep_library_travel_prefetch_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=travelprefetch"
    status, body, _, _ = fetch(
        base_url,
        prep_library_travel_prefetch_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_travel_prefetch_path} returned {status}, expected 200")

    prep_library_travel_prefetch = json.loads(body)
    if not (prep_library_travel_prefetch.get("items") or []):
        raise AssertionError("prep-library travelprefetch search did not expose any governed packet")
    prep_library_travel_prefetches_path = f"/api/v1/campaign-spine/me/workspaces/{workspace_id}/prep-library?queryText=travelprefetches"
    status, body, _, _ = fetch(
        base_url,
        prep_library_travel_prefetches_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{prep_library_travel_prefetches_path} returned {status}, expected 200")

    prep_library_travel_prefetches = json.loads(body)
    if not (prep_library_travel_prefetches.get("items") or []):
        raise AssertionError("prep-library travelprefetches search did not expose any governed packet")

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
        r'href="([^"]*(?:/artifacts/(?:publications|creator)/|/account/work/publications/)[^"]+)"',
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
    home_publication_base_path, _ = split_fragment_path(home_publication_detail_path)
    status, home_publication_body, _, _ = fetch(
        base_url,
        home_publication_base_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{home_publication_detail_path} returned {status}, expected 200")
    require_creator_publication_body(home_publication_body, home_publication_detail_path)
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
            required_texts=("First playable session", "Playable kickoff", "Legal runner", "Understandable return", "Campaign-ready lane"),
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
    workspace_oppositions_search_path = f"{workspace_path}?prepQuery=oppositions"
    status, body, _, _ = fetch(
        base_url,
        workspace_oppositions_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_oppositions_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_oppositions_search_path)
    require_snippet(body, 'match(es) for "oppositions"', workspace_oppositions_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_oppositions_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_oppositions_search_path} should return at least one governed prep packet for the oppositions query")
    workspace_encounter_search_path = f"{workspace_path}?prepQuery=encounter"
    status, body, _, _ = fetch(
        base_url,
        workspace_encounter_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_encounter_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_encounter_search_path)
    require_snippet(body, 'match(es) for "encounter"', workspace_encounter_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_encounter_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_encounter_search_path} should return at least one governed prep packet for the encounter query")
    workspace_enemy_search_path = f"{workspace_path}?prepQuery=enemy"
    status, body, _, _ = fetch(
        base_url,
        workspace_enemy_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_enemy_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_enemy_search_path)
    require_snippet(body, 'match(es) for "enemy"', workspace_enemy_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_enemy_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_enemy_search_path} should return at least one governed prep packet for the enemy query")
    workspace_hostile_search_path = f"{workspace_path}?prepQuery=hostile"
    status, body, _, _ = fetch(
        base_url,
        workspace_hostile_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_hostile_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_hostile_search_path)
    require_snippet(body, 'match(es) for "hostile"', workspace_hostile_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_hostile_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_hostile_search_path} should return at least one governed prep packet for the hostile query")
    workspace_adversary_search_path = f"{workspace_path}?prepQuery=adversary"
    status, body, _, _ = fetch(
        base_url,
        workspace_adversary_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_adversary_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_adversary_search_path)
    require_snippet(body, 'match(es) for "adversary"', workspace_adversary_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_adversary_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_adversary_search_path} should return at least one governed prep packet for the adversary query")
    workspace_threat_search_path = f"{workspace_path}?prepQuery=threat"
    status, body, _, _ = fetch(
        base_url,
        workspace_threat_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_threat_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_threat_search_path)
    require_snippet(body, 'match(es) for "threat"', workspace_threat_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_threat_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_threat_search_path} should return at least one governed prep packet for the threat query")
    workspace_opfor_search_path = f"{workspace_path}?prepQuery=opfor"
    status, body, _, _ = fetch(
        base_url,
        workspace_opfor_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_opfor_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_opfor_search_path)
    require_snippet(body, 'match(es) for "opfor"', workspace_opfor_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_opfor_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_opfor_search_path} should return at least one governed prep packet for the opfor query")
    workspace_opforce_search_path = f"{workspace_path}?prepQuery=opforce"
    status, body, _, _ = fetch(
        base_url,
        workspace_opforce_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_opforce_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_opforce_search_path)
    require_snippet(body, 'match(es) for "opforce"', workspace_opforce_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_opforce_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_opforce_search_path} should return at least one governed prep packet for the opforce query")
    workspace_opforces_search_path = f"{workspace_path}?prepQuery=opforces"
    status, body, _, _ = fetch(
        base_url,
        workspace_opforces_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_opforces_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_opforces_search_path)
    require_snippet(body, 'match(es) for "opforces"', workspace_opforces_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_opforces_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_opforces_search_path} should return at least one governed prep packet for the opforces query")
    workspace_opfors_search_path = f"{workspace_path}?prepQuery=opfors"
    status, body, _, _ = fetch(
        base_url,
        workspace_opfors_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_opfors_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_opfors_search_path)
    require_snippet(body, 'match(es) for "opfors"', workspace_opfors_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_opfors_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_opfors_search_path} should return at least one governed prep packet for the opfors query")
    workspace_op_force_search_path = f"{workspace_path}?prepQuery=op-force"
    status, body, _, _ = fetch(
        base_url,
        workspace_op_force_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_op_force_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_op_force_search_path)
    require_snippet(body, 'match(es) for "op-force"', workspace_op_force_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_op_force_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_op_force_search_path} should return at least one governed prep packet for the op-force query")
    workspace_op_space_force_search_path = f"{workspace_path}?prepQuery=op%20force"
    status, body, _, _ = fetch(
        base_url,
        workspace_op_space_force_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_op_space_force_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_op_space_force_search_path)
    require_snippet(body, 'match(es) for "op force"', workspace_op_space_force_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_op_space_force_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_op_space_force_search_path} should return at least one governed prep packet for the op force query")
    workspace_season_search_path = f"{workspace_path}?prepQuery=seasonops"
    status, body, _, _ = fetch(
        base_url,
        workspace_season_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_season_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_season_search_path)
    require_snippet(body, 'match(es) for "seasonops"', workspace_season_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_season_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_season_search_path} should return at least one governed prep packet for the seasonops query")
    workspace_seasonop_search_path = f"{workspace_path}?prepQuery=seasonop"
    status, body, _, _ = fetch(
        base_url,
        workspace_seasonop_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_seasonop_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_seasonop_search_path)
    require_snippet(body, 'match(es) for "seasonop"', workspace_seasonop_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_seasonop_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_seasonop_search_path} should return at least one governed prep packet for the seasonop query")
    workspace_season_operation_search_path = f"{workspace_path}?prepQuery=season-operation"
    status, body, _, _ = fetch(
        base_url,
        workspace_season_operation_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_season_operation_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_season_operation_search_path)
    require_snippet(body, 'match(es) for "season-operation"', workspace_season_operation_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_season_operation_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_season_operation_search_path} should return at least one governed prep packet for the season-operation query")
    workspace_season_operations_search_path = f"{workspace_path}?prepQuery=season-operations"
    status, body, _, _ = fetch(
        base_url,
        workspace_season_operations_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_season_operations_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_season_operations_search_path)
    require_snippet(body, 'match(es) for "season-operations"', workspace_season_operations_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_season_operations_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_season_operations_search_path} should return at least one governed prep packet for the season-operations query")
    workspace_seasoncontrol_search_path = f"{workspace_path}?prepQuery=seasoncontrol"
    status, body, _, _ = fetch(
        base_url,
        workspace_seasoncontrol_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_seasoncontrol_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_seasoncontrol_search_path)
    require_snippet(body, 'match(es) for "seasoncontrol"', workspace_seasoncontrol_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_seasoncontrol_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_seasoncontrol_search_path} should return at least one governed prep packet for the seasoncontrol query")
    workspace_season_control_search_path = f"{workspace_path}?prepQuery=season%20control"
    status, body, _, _ = fetch(
        base_url,
        workspace_season_control_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_season_control_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_season_control_search_path)
    require_snippet(body, 'match(es) for "season control"', workspace_season_control_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_season_control_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_season_control_search_path} should return at least one governed prep packet for the season control query")
    workspace_seasoncontrols_search_path = f"{workspace_path}?prepQuery=seasoncontrols"
    status, body, _, _ = fetch(
        base_url,
        workspace_seasoncontrols_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_seasoncontrols_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_seasoncontrols_search_path)
    require_snippet(body, 'match(es) for "seasoncontrols"', workspace_seasoncontrols_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_seasoncontrols_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_seasoncontrols_search_path} should return at least one governed prep packet for the seasoncontrols query")
    workspace_seasonctrl_search_path = f"{workspace_path}?prepQuery=seasonctrl"
    status, body, _, _ = fetch(
        base_url,
        workspace_seasonctrl_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_seasonctrl_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_seasonctrl_search_path)
    require_snippet(body, 'match(es) for "seasonctrl"', workspace_seasonctrl_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_seasonctrl_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_seasonctrl_search_path} should return at least one governed prep packet for the seasonctrl query")
    workspace_seasonctl_search_path = f"{workspace_path}?prepQuery=seasonctl"
    status, body, _, _ = fetch(
        base_url,
        workspace_seasonctl_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header, "Accept-Language": "en-US"},
    )
    if status != 200:
        raise AssertionError(f"{workspace_seasonctl_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_seasonctl_search_path)
    require_snippet(body, 'match(es) for "seasonctl"', workspace_seasonctl_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_seasonctl_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_seasonctl_search_path} should return at least one governed prep packet for the seasonctl query")
    workspace_seasonctls_search_path = f"{workspace_path}?prepQuery=seasonctls"
    status, body, _, _ = fetch(
        base_url,
        workspace_seasonctls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header, "Accept-Language": "en-US"},
    )
    if status != 200:
        raise AssertionError(f"{workspace_seasonctls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_seasonctls_search_path)
    require_snippet(body, 'match(es) for "seasonctls"', workspace_seasonctls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_seasonctls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_seasonctls_search_path} should return at least one governed prep packet for the seasonctls query")
    workspace_season_ctls_search_path = f"{workspace_path}?prepQuery=season%20ctls"
    status, body, _, _ = fetch(
        base_url,
        workspace_season_ctls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_season_ctls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_season_ctls_search_path)
    require_snippet(body, 'match(es) for "season ctls"', workspace_season_ctls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_season_ctls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_season_ctls_search_path} should return at least one governed prep packet for the season ctls query")
    workspace_seasonctrls_search_path = f"{workspace_path}?prepQuery=seasonctrls"
    status, body, _, _ = fetch(
        base_url,
        workspace_seasonctrls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_seasonctrls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_seasonctrls_search_path)
    require_snippet(body, 'match(es) for "seasonctrls"', workspace_seasonctrls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_seasonctrls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_seasonctrls_search_path} should return at least one governed prep packet for the seasonctrls query")
    workspace_eventcontrol_search_path = f"{workspace_path}?prepQuery=eventcontrol"
    status, body, _, _ = fetch(
        base_url,
        workspace_eventcontrol_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_eventcontrol_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_eventcontrol_search_path)
    require_snippet(body, 'match(es) for "eventcontrol"', workspace_eventcontrol_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_eventcontrol_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_eventcontrol_search_path} should return at least one governed prep packet for the eventcontrol query")
    workspace_eventcontrols_search_path = f"{workspace_path}?prepQuery=eventcontrols"
    status, body, _, _ = fetch(
        base_url,
        workspace_eventcontrols_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_eventcontrols_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_eventcontrols_search_path)
    require_snippet(body, 'match(es) for "eventcontrols"', workspace_eventcontrols_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_eventcontrols_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_eventcontrols_search_path} should return at least one governed prep packet for the eventcontrols query")
    workspace_event_control_search_path = f"{workspace_path}?prepQuery=event%20control"
    status, body, _, _ = fetch(
        base_url,
        workspace_event_control_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_event_control_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_event_control_search_path)
    require_snippet(body, 'match(es) for "event control"', workspace_event_control_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_event_control_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_event_control_search_path} should return at least one governed prep packet for the event control query")
    workspace_event_controls_search_path = f"{workspace_path}?prepQuery=event%20controls"
    status, body, _, _ = fetch(
        base_url,
        workspace_event_controls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_event_controls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_event_controls_search_path)
    require_snippet(body, 'match(es) for "event controls"', workspace_event_controls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_event_controls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_event_controls_search_path} should return at least one governed prep packet for the event controls query")
    workspace_event_control_hyphen_search_path = f"{workspace_path}?prepQuery=event-control"
    status, body, _, _ = fetch(
        base_url,
        workspace_event_control_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_event_control_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_event_control_hyphen_search_path)
    require_snippet(body, 'match(es) for "event-control"', workspace_event_control_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_event_control_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_event_control_hyphen_search_path} should return at least one governed prep packet for the event-control query")
    workspace_event_ctrl_search_path = f"{workspace_path}?prepQuery=event%20ctrl"
    status, body, _, _ = fetch(
        base_url,
        workspace_event_ctrl_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_event_ctrl_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_event_ctrl_search_path)
    require_snippet(body, 'match(es) for "event ctrl"', workspace_event_ctrl_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_event_ctrl_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_event_ctrl_search_path} should return at least one governed prep packet for the event ctrl query")
    workspace_event_ctrl_hyphen_search_path = f"{workspace_path}?prepQuery=event-ctrl"
    status, body, _, _ = fetch(
        base_url,
        workspace_event_ctrl_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_event_ctrl_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_event_ctrl_hyphen_search_path)
    require_snippet(body, 'match(es) for "event-ctrl"', workspace_event_ctrl_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_event_ctrl_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_event_ctrl_hyphen_search_path} should return at least one governed prep packet for the event-ctrl query")
    workspace_eventctrl_search_path = f"{workspace_path}?prepQuery=eventctrl"
    status, body, _, _ = fetch(
        base_url,
        workspace_eventctrl_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_eventctrl_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_eventctrl_search_path)
    require_snippet(body, 'match(es) for "eventctrl"', workspace_eventctrl_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_eventctrl_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_eventctrl_search_path} should return at least one governed prep packet for the eventctrl query")
    workspace_eventctl_search_path = f"{workspace_path}?prepQuery=eventctl"
    status, body, _, _ = fetch(
        base_url,
        workspace_eventctl_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header, "Accept-Language": "en-US"},
    )
    if status != 200:
        raise AssertionError(f"{workspace_eventctl_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_eventctl_search_path)
    require_snippet(body, 'match(es) for "eventctl"', workspace_eventctl_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_eventctl_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_eventctl_search_path} should return at least one governed prep packet for the eventctl query")
    workspace_eventctls_search_path = f"{workspace_path}?prepQuery=eventctls"
    status, body, _, _ = fetch(
        base_url,
        workspace_eventctls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header, "Accept-Language": "en-US"},
    )
    if status != 200:
        raise AssertionError(f"{workspace_eventctls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_eventctls_search_path)
    require_snippet(body, 'match(es) for "eventctls"', workspace_eventctls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_eventctls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_eventctls_search_path} should return at least one governed prep packet for the eventctls query")
    workspace_event_ctls_search_path = f"{workspace_path}?prepQuery=event%20ctls"
    status, body, _, _ = fetch(
        base_url,
        workspace_event_ctls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_event_ctls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_event_ctls_search_path)
    require_snippet(body, 'match(es) for "event ctls"', workspace_event_ctls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_event_ctls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_event_ctls_search_path} should return at least one governed prep packet for the event ctls query")
    workspace_eventctrls_search_path = f"{workspace_path}?prepQuery=eventctrls"
    status, body, _, _ = fetch(
        base_url,
        workspace_eventctrls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_eventctrls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_eventctrls_search_path)
    require_snippet(body, 'match(es) for "eventctrls"', workspace_eventctrls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_eventctrls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_eventctrls_search_path} should return at least one governed prep packet for the eventctrls query")
    workspace_eventops_search_path = f"{workspace_path}?prepQuery=eventops"
    status, body, _, _ = fetch(
        base_url,
        workspace_eventops_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_eventops_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_eventops_search_path)
    require_snippet(body, 'match(es) for "eventops"', workspace_eventops_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_eventops_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_eventops_search_path} should return at least one governed prep packet for the eventops query")
    workspace_event_ops_search_path = f"{workspace_path}?prepQuery=event%20ops"
    status, body, _, _ = fetch(
        base_url,
        workspace_event_ops_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_event_ops_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_event_ops_search_path)
    require_snippet(body, 'match(es) for "event ops"', workspace_event_ops_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_event_ops_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_event_ops_search_path} should return at least one governed prep packet for the event ops query")
    workspace_eventop_search_path = f"{workspace_path}?prepQuery=eventop"
    status, body, _, _ = fetch(
        base_url,
        workspace_eventop_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_eventop_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_eventop_search_path)
    require_snippet(body, 'match(es) for "eventop"', workspace_eventop_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_eventop_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_eventop_search_path} should return at least one governed prep packet for the eventop query")
    workspace_eventoperation_search_path = f"{workspace_path}?prepQuery=eventoperation"
    status, body, _, _ = fetch(
        base_url,
        workspace_eventoperation_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_eventoperation_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_eventoperation_search_path)
    require_snippet(body, 'match(es) for "eventoperation"', workspace_eventoperation_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_eventoperation_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_eventoperation_search_path} should return at least one governed prep packet for the eventoperation query")
    workspace_eventoperations_search_path = f"{workspace_path}?prepQuery=eventoperations"
    status, body, _, _ = fetch(
        base_url,
        workspace_eventoperations_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_eventoperations_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_eventoperations_search_path)
    require_snippet(body, 'match(es) for "eventoperations"', workspace_eventoperations_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_eventoperations_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_eventoperations_search_path} should return at least one governed prep packet for the eventoperations query")
    workspace_event_op_hyphen_search_path = f"{workspace_path}?prepQuery=event-op"
    status, body, _, _ = fetch(
        base_url,
        workspace_event_op_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_event_op_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_event_op_hyphen_search_path)
    require_snippet(body, 'match(es) for "event-op"', workspace_event_op_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_event_op_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_event_op_hyphen_search_path} should return at least one governed prep packet for the event-op query")
    workspace_event_operation_search_path = f"{workspace_path}?prepQuery=event-operation"
    status, body, _, _ = fetch(
        base_url,
        workspace_event_operation_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_event_operation_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_event_operation_search_path)
    require_snippet(body, 'match(es) for "event-operation"', workspace_event_operation_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_event_operation_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_event_operation_search_path} should return at least one governed prep packet for the event-operation query")
    workspace_event_operations_search_path = f"{workspace_path}?prepQuery=event-operations"
    status, body, _, _ = fetch(
        base_url,
        workspace_event_operations_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_event_operations_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_event_operations_search_path)
    require_snippet(body, 'match(es) for "event-operations"', workspace_event_operations_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_event_operations_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_event_operations_search_path} should return at least one governed prep packet for the event-operations query")
    workspace_gmops_search_path = f"{workspace_path}?prepQuery=gmops"
    status, body, _, _ = fetch(
        base_url,
        workspace_gmops_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gmops_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gmops_search_path)
    require_snippet(body, 'match(es) for "gmops"', workspace_gmops_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gmops_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gmops_search_path} should return at least one governed prep packet for the gmops query")
    workspace_gm_ops_search_path = f"{workspace_path}?prepQuery=gm%20ops"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_ops_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_ops_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_ops_search_path)
    require_snippet(body, 'match(es) for "gm ops"', workspace_gm_ops_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_ops_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_ops_search_path} should return at least one governed prep packet for the gm ops query")
    workspace_gm_ops_hyphen_search_path = f"{workspace_path}?prepQuery=gm-ops"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_ops_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_ops_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_ops_hyphen_search_path)
    require_snippet(body, 'match(es) for "gm-ops"', workspace_gm_ops_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_ops_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_ops_hyphen_search_path} should return at least one governed prep packet for the gm-ops query")
    workspace_gmop_search_path = f"{workspace_path}?prepQuery=gmop"
    status, body, _, _ = fetch(
        base_url,
        workspace_gmop_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gmop_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gmop_search_path)
    require_snippet(body, 'match(es) for "gmop"', workspace_gmop_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gmop_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gmop_search_path} should return at least one governed prep packet for the gmop query")
    workspace_gm_op_hyphen_search_path = f"{workspace_path}?prepQuery=gm-op"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_op_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_op_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_op_hyphen_search_path)
    require_snippet(body, 'match(es) for "gm-op"', workspace_gm_op_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_op_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_op_hyphen_search_path} should return at least one governed prep packet for the gm-op query")
    workspace_gm_operation_compact_search_path = f"{workspace_path}?prepQuery=gmoperation"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_operation_compact_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_operation_compact_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_operation_compact_search_path)
    require_snippet(body, 'match(es) for "gmoperation"', workspace_gm_operation_compact_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_operation_compact_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_operation_compact_search_path} should return at least one governed prep packet for the gmoperation query")
    workspace_gm_operations_compact_search_path = f"{workspace_path}?prepQuery=gmoperations"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_operations_compact_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_operations_compact_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_operations_compact_search_path)
    require_snippet(body, 'match(es) for "gmoperations"', workspace_gm_operations_compact_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_operations_compact_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_operations_compact_search_path} should return at least one governed prep packet for the gmoperations query")
    workspace_gm_operation_split_search_path = f"{workspace_path}?prepQuery=gm%20operation"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_operation_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_operation_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_operation_split_search_path)
    require_snippet(body, 'match(es) for "gm operation"', workspace_gm_operation_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_operation_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_operation_split_search_path} should return at least one governed prep packet for the gm operation query")
    workspace_gm_operation_hyphen_search_path = f"{workspace_path}?prepQuery=gm-operation"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_operation_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_operation_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_operation_hyphen_search_path)
    require_snippet(body, 'match(es) for "gm-operation"', workspace_gm_operation_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_operation_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_operation_hyphen_search_path} should return at least one governed prep packet for the gm-operation query")
    workspace_gm_operations_split_search_path = f"{workspace_path}?prepQuery=gm%20operations"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_operations_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_operations_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_operations_split_search_path)
    require_snippet(body, 'match(es) for "gm operations"', workspace_gm_operations_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_operations_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_operations_split_search_path} should return at least one governed prep packet for the gm operations query")
    workspace_gm_operations_hyphen_search_path = f"{workspace_path}?prepQuery=gm-operations"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_operations_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_operations_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_operations_hyphen_search_path)
    require_snippet(body, 'match(es) for "gm-operations"', workspace_gm_operations_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_operations_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_operations_hyphen_search_path} should return at least one governed prep packet for the gm-operations query")
    workspace_gmcontrol_compact_search_path = f"{workspace_path}?prepQuery=gmcontrol"
    status, body, _, _ = fetch(
        base_url,
        workspace_gmcontrol_compact_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gmcontrol_compact_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gmcontrol_compact_search_path)
    require_snippet(body, 'match(es) for "gmcontrol"', workspace_gmcontrol_compact_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gmcontrol_compact_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gmcontrol_compact_search_path} should return at least one governed prep packet for the gmcontrol query")
    workspace_gmcontrols_compact_search_path = f"{workspace_path}?prepQuery=gmcontrols"
    status, body, _, _ = fetch(
        base_url,
        workspace_gmcontrols_compact_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gmcontrols_compact_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gmcontrols_compact_search_path)
    require_snippet(body, 'match(es) for "gmcontrols"', workspace_gmcontrols_compact_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gmcontrols_compact_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gmcontrols_compact_search_path} should return at least one governed prep packet for the gmcontrols query")
    workspace_gmctrl_compact_search_path = f"{workspace_path}?prepQuery=gmctrl"
    status, body, _, _ = fetch(
        base_url,
        workspace_gmctrl_compact_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gmctrl_compact_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gmctrl_compact_search_path)
    require_snippet(body, 'match(es) for "gmctrl"', workspace_gmctrl_compact_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gmctrl_compact_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gmctrl_compact_search_path} should return at least one governed prep packet for the gmctrl query")
    workspace_gmctrls_compact_search_path = f"{workspace_path}?prepQuery=gmctrls"
    status, body, _, _ = fetch(
        base_url,
        workspace_gmctrls_compact_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gmctrls_compact_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gmctrls_compact_search_path)
    require_snippet(body, 'match(es) for "gmctrls"', workspace_gmctrls_compact_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gmctrls_compact_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gmctrls_compact_search_path} should return at least one governed prep packet for the gmctrls query")
    workspace_gmctl_compact_search_path = f"{workspace_path}?prepQuery=gmctl"
    status, body, _, _ = fetch(
        base_url,
        workspace_gmctl_compact_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gmctl_compact_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gmctl_compact_search_path)
    require_snippet(body, 'match(es) for "gmctl"', workspace_gmctl_compact_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gmctl_compact_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gmctl_compact_search_path} should return at least one governed prep packet for the gmctl query")
    workspace_gmctls_compact_search_path = f"{workspace_path}?prepQuery=gmctls"
    status, body, _, _ = fetch(
        base_url,
        workspace_gmctls_compact_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gmctls_compact_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gmctls_compact_search_path)
    require_snippet(body, 'match(es) for "gmctls"', workspace_gmctls_compact_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gmctls_compact_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gmctls_compact_search_path} should return at least one governed prep packet for the gmctls query")
    workspace_gm_ctls_hyphen_search_path = f"{workspace_path}?prepQuery=gm-ctls"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_ctls_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_ctls_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_ctls_hyphen_search_path)
    require_snippet(body, 'match(es) for "gm-ctls"', workspace_gm_ctls_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_ctls_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_ctls_hyphen_search_path} should return at least one governed prep packet for the gm-ctls query")
    workspace_gm_ctls_split_search_path = f"{workspace_path}?prepQuery=gm%20ctls"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_ctls_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_ctls_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_ctls_split_search_path)
    require_snippet(body, 'match(es) for "gm ctls"', workspace_gm_ctls_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_ctls_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_ctls_split_search_path} should return at least one governed prep packet for the gm ctls query")
    workspace_gm_ctrls_split_search_path = f"{workspace_path}?prepQuery=gm%20ctrls"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_ctrls_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_ctrls_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_ctrls_split_search_path)
    require_snippet(body, 'match(es) for "gm ctrls"', workspace_gm_ctrls_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_ctrls_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_ctrls_split_search_path} should return at least one governed prep packet for the gm ctrls query")
    workspace_gm_ctl_split_search_path = f"{workspace_path}?prepQuery=gm%20ctl"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_ctl_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_ctl_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_ctl_split_search_path)
    require_snippet(body, 'match(es) for "gm ctl"', workspace_gm_ctl_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_ctl_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_ctl_split_search_path} should return at least one governed prep packet for the gm ctl query")
    workspace_gm_ctl_hyphen_search_path = f"{workspace_path}?prepQuery=gm-ctl"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_ctl_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_ctl_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_ctl_hyphen_search_path)
    require_snippet(body, 'match(es) for "gm-ctl"', workspace_gm_ctl_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_ctl_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_ctl_hyphen_search_path} should return at least one governed prep packet for the gm-ctl query")
    workspace_gm_control_split_search_path = f"{workspace_path}?prepQuery=gm%20control"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_control_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_control_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_control_split_search_path)
    require_snippet(body, 'match(es) for "gm control"', workspace_gm_control_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_control_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_control_split_search_path} should return at least one governed prep packet for the gm control query")
    workspace_gm_control_hyphen_search_path = f"{workspace_path}?prepQuery=gm-control"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_control_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_control_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_control_hyphen_search_path)
    require_snippet(body, 'match(es) for "gm-control"', workspace_gm_control_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_control_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_control_hyphen_search_path} should return at least one governed prep packet for the gm-control query")
    workspace_gm_controls_split_search_path = f"{workspace_path}?prepQuery=gm%20controls"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_controls_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_controls_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_controls_split_search_path)
    require_snippet(body, 'match(es) for "gm controls"', workspace_gm_controls_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_controls_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_controls_split_search_path} should return at least one governed prep packet for the gm controls query")
    workspace_gm_controls_hyphen_search_path = f"{workspace_path}?prepQuery=gm-controls"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_controls_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_controls_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_controls_hyphen_search_path)
    require_snippet(body, 'match(es) for "gm-controls"', workspace_gm_controls_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_controls_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_controls_hyphen_search_path} should return at least one governed prep packet for the gm-controls query")
    workspace_gm_ctrl_split_search_path = f"{workspace_path}?prepQuery=gm%20ctrl"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_ctrl_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_ctrl_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_ctrl_split_search_path)
    require_snippet(body, 'match(es) for "gm ctrl"', workspace_gm_ctrl_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_ctrl_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_ctrl_split_search_path} should return at least one governed prep packet for the gm ctrl query")
    workspace_gm_ctrl_hyphen_search_path = f"{workspace_path}?prepQuery=gm-ctrl"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_ctrl_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_ctrl_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_ctrl_hyphen_search_path)
    require_snippet(body, 'match(es) for "gm-ctrl"', workspace_gm_ctrl_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_ctrl_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_ctrl_hyphen_search_path} should return at least one governed prep packet for the gm-ctrl query")
    workspace_gm_ctrls_hyphen_search_path = f"{workspace_path}?prepQuery=gm-ctrls"
    status, body, _, _ = fetch(
        base_url,
        workspace_gm_ctrls_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_gm_ctrls_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_gm_ctrls_hyphen_search_path)
    require_snippet(body, 'match(es) for "gm-ctrls"', workspace_gm_ctrls_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_gm_ctrls_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_gm_ctrls_hyphen_search_path} should return at least one governed prep packet for the gm-ctrls query")
    workspace_leagueops_search_path = f"{workspace_path}?prepQuery=leagueops"
    status, body, _, _ = fetch(
        base_url,
        workspace_leagueops_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_leagueops_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_leagueops_search_path)
    require_snippet(body, 'match(es) for "leagueops"', workspace_leagueops_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_leagueops_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_leagueops_search_path} should return at least one governed prep packet for the leagueops query")
    workspace_leagueop_search_path = f"{workspace_path}?prepQuery=leagueop"
    status, body, _, _ = fetch(
        base_url,
        workspace_leagueop_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_leagueop_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_leagueop_search_path)
    require_snippet(body, 'match(es) for "leagueop"', workspace_leagueop_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_leagueop_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_leagueop_search_path} should return at least one governed prep packet for the leagueop query")
    workspace_leagueoperation_search_path = f"{workspace_path}?prepQuery=leagueoperation"
    status, body, _, _ = fetch(
        base_url,
        workspace_leagueoperation_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_leagueoperation_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_leagueoperation_search_path)
    require_snippet(body, 'match(es) for "leagueoperation"', workspace_leagueoperation_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_leagueoperation_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_leagueoperation_search_path} should return at least one governed prep packet for the leagueoperation query")
    workspace_league_op_hyphen_search_path = f"{workspace_path}?prepQuery=league-op"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_op_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_op_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_op_hyphen_search_path)
    require_snippet(body, 'match(es) for "league-op"', workspace_league_op_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_op_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_op_hyphen_search_path} should return at least one governed prep packet for the league-op query")
    workspace_league_operation_hyphen_search_path = f"{workspace_path}?prepQuery=league-operation"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_operation_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_operation_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_operation_hyphen_search_path)
    require_snippet(body, 'match(es) for "league-operation"', workspace_league_operation_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_operation_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_operation_hyphen_search_path} should return at least one governed prep packet for the league-operation query")
    workspace_leagueoperations_search_path = f"{workspace_path}?prepQuery=leagueoperations"
    status, body, _, _ = fetch(
        base_url,
        workspace_leagueoperations_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_leagueoperations_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_leagueoperations_search_path)
    require_snippet(body, 'match(es) for "leagueoperations"', workspace_leagueoperations_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_leagueoperations_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_leagueoperations_search_path} should return at least one governed prep packet for the leagueoperations query")
    workspace_league_operations_hyphen_search_path = f"{workspace_path}?prepQuery=league-operations"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_operations_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_operations_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_operations_hyphen_search_path)
    require_snippet(body, 'match(es) for "league-operations"', workspace_league_operations_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_operations_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_operations_hyphen_search_path} should return at least one governed prep packet for the league-operations query")
    workspace_league_ops_search_path = f"{workspace_path}?prepQuery=league%20ops"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_ops_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_ops_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_ops_search_path)
    require_snippet(body, 'match(es) for "league ops"', workspace_league_ops_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_ops_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_ops_search_path} should return at least one governed prep packet for the league ops query")
    workspace_league_op_search_path = f"{workspace_path}?prepQuery=league%20op"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_op_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_op_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_op_search_path)
    require_snippet(body, 'match(es) for "league op"', workspace_league_op_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_op_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_op_search_path} should return at least one governed prep packet for the league op query")
    workspace_league_ops_hyphen_search_path = f"{workspace_path}?prepQuery=league-ops"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_ops_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_ops_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_ops_hyphen_search_path)
    require_snippet(body, 'match(es) for "league-ops"', workspace_league_ops_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_ops_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_ops_hyphen_search_path} should return at least one governed prep packet for the league-ops query")
    workspace_leaguecontrol_search_path = f"{workspace_path}?prepQuery=leaguecontrol"
    status, body, _, _ = fetch(
        base_url,
        workspace_leaguecontrol_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_leaguecontrol_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_leaguecontrol_search_path)
    require_snippet(body, 'match(es) for "leaguecontrol"', workspace_leaguecontrol_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_leaguecontrol_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_leaguecontrol_search_path} should return at least one governed prep packet for the leaguecontrol query")
    workspace_league_controls_search_path = f"{workspace_path}?prepQuery=league%20controls"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_controls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_controls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_controls_search_path)
    require_snippet(body, 'match(es) for "league controls"', workspace_league_controls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_controls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_controls_search_path} should return at least one governed prep packet for the league controls query")
    workspace_leaguecontrols_search_path = f"{workspace_path}?prepQuery=leaguecontrols"
    status, body, _, _ = fetch(
        base_url,
        workspace_leaguecontrols_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_leaguecontrols_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_leaguecontrols_search_path)
    require_snippet(body, 'match(es) for "leaguecontrols"', workspace_leaguecontrols_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_leaguecontrols_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_leaguecontrols_search_path} should return at least one governed prep packet for the leaguecontrols query")
    workspace_league_control_search_path = f"{workspace_path}?prepQuery=league%20control"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_control_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_control_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_control_search_path)
    require_snippet(body, 'match(es) for "league control"', workspace_league_control_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_control_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_control_search_path} should return at least one governed prep packet for the league control query")
    workspace_league_control_hyphen_search_path = f"{workspace_path}?prepQuery=league-control"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_control_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_control_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_control_hyphen_search_path)
    require_snippet(body, 'match(es) for "league-control"', workspace_league_control_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_control_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_control_hyphen_search_path} should return at least one governed prep packet for the league-control query")
    workspace_leaguectrl_search_path = f"{workspace_path}?prepQuery=leaguectrl"
    status, body, _, _ = fetch(
        base_url,
        workspace_leaguectrl_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_leaguectrl_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_leaguectrl_search_path)
    require_snippet(body, 'match(es) for "leaguectrl"', workspace_leaguectrl_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_leaguectrl_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_leaguectrl_search_path} should return at least one governed prep packet for the leaguectrl query")
    workspace_leaguectl_search_path = f"{workspace_path}?prepQuery=leaguectl"
    status, body, _, _ = fetch(
        base_url,
        workspace_leaguectl_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_leaguectl_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_leaguectl_search_path)
    require_snippet(body, 'match(es) for "leaguectl"', workspace_leaguectl_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_leaguectl_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_leaguectl_search_path} should return at least one governed prep packet for the leaguectl query")
    workspace_leaguectls_search_path = f"{workspace_path}?prepQuery=leaguectls"
    status, body, _, _ = fetch(
        base_url,
        workspace_leaguectls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_leaguectls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_leaguectls_search_path)
    require_snippet(body, 'match(es) for "leaguectls"', workspace_leaguectls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_leaguectls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_leaguectls_search_path} should return at least one governed prep packet for the leaguectls query")
    workspace_leaguectrls_search_path = f"{workspace_path}?prepQuery=leaguectrls"
    status, body, _, _ = fetch(
        base_url,
        workspace_leaguectrls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_leaguectrls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_leaguectrls_search_path)
    require_snippet(body, 'match(es) for "leaguectrls"', workspace_leaguectrls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_leaguectrls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_leaguectrls_search_path} should return at least one governed prep packet for the leaguectrls query")
    workspace_league_ctl_search_path = f"{workspace_path}?prepQuery=league%20ctl"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_ctl_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_ctl_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_ctl_search_path)
    require_snippet(body, 'match(es) for "league ctl"', workspace_league_ctl_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_ctl_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_ctl_search_path} should return at least one governed prep packet for the league ctl query")
    workspace_league_ctl_hyphen_search_path = f"{workspace_path}?prepQuery=league-ctl"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_ctl_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_ctl_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_ctl_hyphen_search_path)
    require_snippet(body, 'match(es) for "league-ctl"', workspace_league_ctl_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_ctl_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_ctl_hyphen_search_path} should return at least one governed prep packet for the league-ctl query")
    workspace_league_ctls_search_path = f"{workspace_path}?prepQuery=league%20ctls"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_ctls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_ctls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_ctls_search_path)
    require_snippet(body, 'match(es) for "league ctls"', workspace_league_ctls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_ctls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_ctls_search_path} should return at least one governed prep packet for the league ctls query")
    workspace_league_ctls_hyphen_search_path = f"{workspace_path}?prepQuery=league-ctls"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_ctls_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_ctls_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_ctls_hyphen_search_path)
    require_snippet(body, 'match(es) for "league-ctls"', workspace_league_ctls_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_ctls_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_ctls_hyphen_search_path} should return at least one governed prep packet for the league-ctls query")
    workspace_league_ctrls_search_path = f"{workspace_path}?prepQuery=league%20ctrls"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_ctrls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_ctrls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_ctrls_search_path)
    require_snippet(body, 'match(es) for "league ctrls"', workspace_league_ctrls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_ctrls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_ctrls_search_path} should return at least one governed prep packet for the league ctrls query")
    workspace_league_ctrls_hyphen_search_path = f"{workspace_path}?prepQuery=league-ctrls"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_ctrls_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_ctrls_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_ctrls_hyphen_search_path)
    require_snippet(body, 'match(es) for "league-ctrls"', workspace_league_ctrls_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_ctrls_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_ctrls_hyphen_search_path} should return at least one governed prep packet for the league-ctrls query")
    workspace_league_ctrl_hyphen_search_path = f"{workspace_path}?prepQuery=league-ctrl"
    status, body, _, _ = fetch(
        base_url,
        workspace_league_ctrl_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_league_ctrl_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_league_ctrl_hyphen_search_path)
    require_snippet(body, 'match(es) for "league-ctrl"', workspace_league_ctrl_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_league_ctrl_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_league_ctrl_hyphen_search_path} should return at least one governed prep packet for the league-ctrl query")
    workspace_communityops_search_path = f"{workspace_path}?prepQuery=communityops"
    status, body, _, _ = fetch(
        base_url,
        workspace_communityops_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_communityops_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_communityops_search_path)
    require_snippet(body, 'match(es) for "communityops"', workspace_communityops_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_communityops_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_communityops_search_path} should return at least one governed prep packet for the communityops query")
    workspace_communityop_search_path = f"{workspace_path}?prepQuery=communityop"
    status, body, _, _ = fetch(
        base_url,
        workspace_communityop_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_communityop_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_communityop_search_path)
    require_snippet(body, 'match(es) for "communityop"', workspace_communityop_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_communityop_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_communityop_search_path} should return at least one governed prep packet for the communityop query")
    workspace_communityoperation_search_path = f"{workspace_path}?prepQuery=communityoperation"
    status, body, _, _ = fetch(
        base_url,
        workspace_communityoperation_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_communityoperation_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_communityoperation_search_path)
    require_snippet(body, 'match(es) for "communityoperation"', workspace_communityoperation_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_communityoperation_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_communityoperation_search_path} should return at least one governed prep packet for the communityoperation query")
    workspace_community_op_hyphen_search_path = f"{workspace_path}?prepQuery=community-op"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_op_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_op_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_op_hyphen_search_path)
    require_snippet(body, 'match(es) for "community-op"', workspace_community_op_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_op_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_op_hyphen_search_path} should return at least one governed prep packet for the community-op query")
    workspace_community_operation_hyphen_search_path = f"{workspace_path}?prepQuery=community-operation"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_operation_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_operation_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_operation_hyphen_search_path)
    require_snippet(body, 'match(es) for "community-operation"', workspace_community_operation_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_operation_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_operation_hyphen_search_path} should return at least one governed prep packet for the community-operation query")
    workspace_communityoperations_search_path = f"{workspace_path}?prepQuery=communityoperations"
    status, body, _, _ = fetch(
        base_url,
        workspace_communityoperations_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_communityoperations_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_communityoperations_search_path)
    require_snippet(body, 'match(es) for "communityoperations"', workspace_communityoperations_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_communityoperations_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_communityoperations_search_path} should return at least one governed prep packet for the communityoperations query")
    workspace_community_operations_hyphen_search_path = f"{workspace_path}?prepQuery=community-operations"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_operations_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_operations_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_operations_hyphen_search_path)
    require_snippet(body, 'match(es) for "community-operations"', workspace_community_operations_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_operations_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_operations_hyphen_search_path} should return at least one governed prep packet for the community-operations query")
    workspace_community_ops_search_path = f"{workspace_path}?prepQuery=community%20ops"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_ops_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_ops_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_ops_search_path)
    require_snippet(body, 'match(es) for "community ops"', workspace_community_ops_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_ops_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_ops_search_path} should return at least one governed prep packet for the community ops query")
    workspace_community_op_search_path = f"{workspace_path}?prepQuery=community%20op"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_op_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_op_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_op_search_path)
    require_snippet(body, 'match(es) for "community op"', workspace_community_op_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_op_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_op_search_path} should return at least one governed prep packet for the community op query")
    workspace_community_ops_hyphen_search_path = f"{workspace_path}?prepQuery=community-ops"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_ops_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_ops_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_ops_hyphen_search_path)
    require_snippet(body, 'match(es) for "community-ops"', workspace_community_ops_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_ops_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_ops_hyphen_search_path} should return at least one governed prep packet for the community-ops query")
    workspace_communitycontrol_search_path = f"{workspace_path}?prepQuery=communitycontrol"
    status, body, _, _ = fetch(
        base_url,
        workspace_communitycontrol_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_communitycontrol_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_communitycontrol_search_path)
    require_snippet(body, 'match(es) for "communitycontrol"', workspace_communitycontrol_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_communitycontrol_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_communitycontrol_search_path} should return at least one governed prep packet for the communitycontrol query")
    workspace_community_controls_search_path = f"{workspace_path}?prepQuery=community%20controls"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_controls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_controls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_controls_search_path)
    require_snippet(body, 'match(es) for "community controls"', workspace_community_controls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_controls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_controls_search_path} should return at least one governed prep packet for the community controls query")
    workspace_communitycontrols_search_path = f"{workspace_path}?prepQuery=communitycontrols"
    status, body, _, _ = fetch(
        base_url,
        workspace_communitycontrols_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_communitycontrols_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_communitycontrols_search_path)
    require_snippet(body, 'match(es) for "communitycontrols"', workspace_communitycontrols_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_communitycontrols_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_communitycontrols_search_path} should return at least one governed prep packet for the communitycontrols query")
    workspace_community_control_search_path = f"{workspace_path}?prepQuery=community%20control"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_control_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_control_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_control_search_path)
    require_snippet(body, 'match(es) for "community control"', workspace_community_control_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_control_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_control_search_path} should return at least one governed prep packet for the community control query")
    workspace_community_control_hyphen_search_path = f"{workspace_path}?prepQuery=community-control"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_control_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_control_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_control_hyphen_search_path)
    require_snippet(body, 'match(es) for "community-control"', workspace_community_control_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_control_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_control_hyphen_search_path} should return at least one governed prep packet for the community-control query")
    workspace_communityctrl_search_path = f"{workspace_path}?prepQuery=communityctrl"
    status, body, _, _ = fetch(
        base_url,
        workspace_communityctrl_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_communityctrl_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_communityctrl_search_path)
    require_snippet(body, 'match(es) for "communityctrl"', workspace_communityctrl_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_communityctrl_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_communityctrl_search_path} should return at least one governed prep packet for the communityctrl query")
    workspace_communityctl_search_path = f"{workspace_path}?prepQuery=communityctl"
    status, body, _, _ = fetch(
        base_url,
        workspace_communityctl_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_communityctl_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_communityctl_search_path)
    require_snippet(body, 'match(es) for "communityctl"', workspace_communityctl_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_communityctl_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_communityctl_search_path} should return at least one governed prep packet for the communityctl query")
    workspace_communityctls_search_path = f"{workspace_path}?prepQuery=communityctls"
    status, body, _, _ = fetch(
        base_url,
        workspace_communityctls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_communityctls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_communityctls_search_path)
    require_snippet(body, 'match(es) for "communityctls"', workspace_communityctls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_communityctls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_communityctls_search_path} should return at least one governed prep packet for the communityctls query")
    workspace_communityctrls_search_path = f"{workspace_path}?prepQuery=communityctrls"
    status, body, _, _ = fetch(
        base_url,
        workspace_communityctrls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_communityctrls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_communityctrls_search_path)
    require_snippet(body, 'match(es) for "communityctrls"', workspace_communityctrls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_communityctrls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_communityctrls_search_path} should return at least one governed prep packet for the communityctrls query")
    workspace_community_ctl_search_path = f"{workspace_path}?prepQuery=community%20ctl"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_ctl_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_ctl_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_ctl_search_path)
    require_snippet(body, 'match(es) for "community ctl"', workspace_community_ctl_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_ctl_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_ctl_search_path} should return at least one governed prep packet for the community ctl query")
    workspace_community_ctl_hyphen_search_path = f"{workspace_path}?prepQuery=community-ctl"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_ctl_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_ctl_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_ctl_hyphen_search_path)
    require_snippet(body, 'match(es) for "community-ctl"', workspace_community_ctl_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_ctl_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_ctl_hyphen_search_path} should return at least one governed prep packet for the community-ctl query")
    workspace_community_ctls_search_path = f"{workspace_path}?prepQuery=community%20ctls"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_ctls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_ctls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_ctls_search_path)
    require_snippet(body, 'match(es) for "community ctls"', workspace_community_ctls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_ctls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_ctls_search_path} should return at least one governed prep packet for the community ctls query")
    workspace_community_ctls_hyphen_search_path = f"{workspace_path}?prepQuery=community-ctls"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_ctls_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_ctls_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_ctls_hyphen_search_path)
    require_snippet(body, 'match(es) for "community-ctls"', workspace_community_ctls_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_ctls_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_ctls_hyphen_search_path} should return at least one governed prep packet for the community-ctls query")
    workspace_community_ctrls_search_path = f"{workspace_path}?prepQuery=community%20ctrls"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_ctrls_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_ctrls_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_ctrls_search_path)
    require_snippet(body, 'match(es) for "community ctrls"', workspace_community_ctrls_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_ctrls_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_ctrls_search_path} should return at least one governed prep packet for the community ctrls query")
    workspace_community_ctrls_hyphen_search_path = f"{workspace_path}?prepQuery=community-ctrls"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_ctrls_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_ctrls_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_ctrls_hyphen_search_path)
    require_snippet(body, 'match(es) for "community-ctrls"', workspace_community_ctrls_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_ctrls_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_ctrls_hyphen_search_path} should return at least one governed prep packet for the community-ctrls query")
    workspace_community_ctrl_hyphen_search_path = f"{workspace_path}?prepQuery=community-ctrl"
    status, body, _, _ = fetch(
        base_url,
        workspace_community_ctrl_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_community_ctrl_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_community_ctrl_hyphen_search_path)
    require_snippet(body, 'match(es) for "community-ctrl"', workspace_community_ctrl_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_community_ctrl_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_community_ctrl_hyphen_search_path} should return at least one governed prep packet for the community-ctrl query")
    workspace_heat_search_path = f"{workspace_path}?prepQuery=heat"
    status, body, _, _ = fetch(
        base_url,
        workspace_heat_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_heat_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_heat_search_path)
    require_snippet(body, 'match(es) for "heat"', workspace_heat_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_heat_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_heat_search_path} should return at least one governed prep packet for the heat query")
    workspace_heats_search_path = f"{workspace_path}?prepQuery=heats"
    status, body, _, _ = fetch(
        base_url,
        workspace_heats_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_heats_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_heats_search_path)
    require_snippet(body, 'match(es) for "heats"', workspace_heats_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_heats_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_heats_search_path} should return at least one governed prep packet for the heats query")
    workspace_contacts_search_path = f"{workspace_path}?prepQuery=contacts"
    status, body, _, _ = fetch(
        base_url,
        workspace_contacts_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_contacts_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_contacts_search_path)
    require_snippet(body, 'match(es) for "contacts"', workspace_contacts_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_contacts_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_contacts_search_path} should return at least one governed prep packet for the contacts query")
    workspace_contact_search_path = f"{workspace_path}?prepQuery=contact"
    status, body, _, _ = fetch(
        base_url,
        workspace_contact_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_contact_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_contact_search_path)
    require_snippet(body, 'match(es) for "contact"', workspace_contact_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_contact_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_contact_search_path} should return at least one governed prep packet for the contact query")
    workspace_connection_search_path = f"{workspace_path}?prepQuery=connection"
    status, body, _, _ = fetch(
        base_url,
        workspace_connection_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_connection_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_connection_search_path)
    require_snippet(body, 'match(es) for "connection"', workspace_connection_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_connection_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_connection_search_path} should return at least one governed prep packet for the connection query")
    workspace_connections_search_path = f"{workspace_path}?prepQuery=connections"
    status, body, _, _ = fetch(
        base_url,
        workspace_connections_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_connections_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_connections_search_path)
    require_snippet(body, 'match(es) for "connections"', workspace_connections_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_connections_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_connections_search_path} should return at least one governed prep packet for the connections query")
    workspace_relationship_search_path = f"{workspace_path}?prepQuery=relationship"
    status, body, _, _ = fetch(
        base_url,
        workspace_relationship_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_relationship_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_relationship_search_path)
    require_snippet(body, 'match(es) for "relationship"', workspace_relationship_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_relationship_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_relationship_search_path} should return at least one governed prep packet for the relationship query")
    workspace_relationships_search_path = f"{workspace_path}?prepQuery=relationships"
    status, body, _, _ = fetch(
        base_url,
        workspace_relationships_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_relationships_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_relationships_search_path)
    require_snippet(body, 'match(es) for "relationships"', workspace_relationships_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_relationships_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_relationships_search_path} should return at least one governed prep packet for the relationships query")
    workspace_faction_search_path = f"{workspace_path}?prepQuery=faction"
    status, body, _, _ = fetch(
        base_url,
        workspace_faction_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_faction_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_faction_search_path)
    require_snippet(body, 'match(es) for "faction"', workspace_faction_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_faction_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_faction_search_path} should return at least one governed prep packet for the faction query")
    workspace_factions_search_path = f"{workspace_path}?prepQuery=factions"
    status, body, _, _ = fetch(
        base_url,
        workspace_factions_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_factions_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_factions_search_path)
    require_snippet(body, 'match(es) for "factions"', workspace_factions_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_factions_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_factions_search_path} should return at least one governed prep packet for the factions query")
    workspace_journal_search_path = f"{workspace_path}?prepQuery=journal"
    status, body, _, _ = fetch(
        base_url,
        workspace_journal_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_journal_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_journal_search_path)
    require_snippet(body, 'match(es) for "journal"', workspace_journal_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_journal_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_journal_search_path} should return at least one governed prep packet for the journal query")
    workspace_journals_search_path = f"{workspace_path}?prepQuery=journals"
    status, body, _, _ = fetch(
        base_url,
        workspace_journals_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_journals_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_journals_search_path)
    require_snippet(body, 'match(es) for "journals"', workspace_journals_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_journals_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_journals_search_path} should return at least one governed prep packet for the journals query")
    workspace_sessionlog_search_path = f"{workspace_path}?prepQuery=sessionlog"
    status, body, _, _ = fetch(
        base_url,
        workspace_sessionlog_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_sessionlog_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_sessionlog_search_path)
    require_snippet(body, 'match(es) for "sessionlog"', workspace_sessionlog_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_sessionlog_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_sessionlog_search_path} should return at least one governed prep packet for the sessionlog query")
    workspace_sessionlogs_search_path = f"{workspace_path}?prepQuery=sessionlogs"
    status, body, _, _ = fetch(
        base_url,
        workspace_sessionlogs_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_sessionlogs_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_sessionlogs_search_path)
    require_snippet(body, 'match(es) for "sessionlogs"', workspace_sessionlogs_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_sessionlogs_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_sessionlogs_search_path} should return at least one governed prep packet for the sessionlogs query")
    workspace_session_logs_search_path = f"{workspace_path}?prepQuery=session%20logs"
    status, body, _, _ = fetch(
        base_url,
        workspace_session_logs_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_session_logs_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_session_logs_search_path)
    require_snippet(body, 'match(es) for "session logs"', workspace_session_logs_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_session_logs_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_session_logs_search_path} should return at least one governed prep packet for the session logs query")
    workspace_diary_search_path = f"{workspace_path}?prepQuery=diary"
    status, body, _, _ = fetch(
        base_url,
        workspace_diary_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_diary_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_diary_search_path)
    require_snippet(body, 'match(es) for "diary"', workspace_diary_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_diary_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_diary_search_path} should return at least one governed prep packet for the diary query")
    workspace_diaries_search_path = f"{workspace_path}?prepQuery=diaries"
    status, body, _, _ = fetch(
        base_url,
        workspace_diaries_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_diaries_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_diaries_search_path)
    require_snippet(body, 'match(es) for "diaries"', workspace_diaries_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_diaries_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_diaries_search_path} should return at least one governed prep packet for the diaries query")
    workspace_downtime_search_path = f"{workspace_path}?prepQuery=downtime"
    status, body, _, _ = fetch(
        base_url,
        workspace_downtime_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_downtime_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_downtime_search_path)
    require_snippet(body, 'match(es) for "downtime"', workspace_downtime_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_downtime_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_downtime_search_path} should return at least one governed prep packet for the downtime query")
    workspace_downtimes_search_path = f"{workspace_path}?prepQuery=downtimes"
    status, body, _, _ = fetch(
        base_url,
        workspace_downtimes_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_downtimes_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_downtimes_search_path)
    require_snippet(body, 'match(es) for "downtimes"', workspace_downtimes_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_downtimes_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_downtimes_search_path} should return at least one governed prep packet for the downtimes query")
    workspace_aftermath_search_path = f"{workspace_path}?prepQuery=aftermath"
    status, body, _, _ = fetch(
        base_url,
        workspace_aftermath_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_aftermath_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_aftermath_search_path)
    require_snippet(body, 'match(es) for "aftermath"', workspace_aftermath_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_aftermath_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_aftermath_search_path} should return at least one governed prep packet for the aftermath query")
    workspace_aftermaths_search_path = f"{workspace_path}?prepQuery=aftermaths"
    status, body, _, _ = fetch(
        base_url,
        workspace_aftermaths_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_aftermaths_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_aftermaths_search_path)
    require_snippet(body, 'match(es) for "aftermaths"', workspace_aftermaths_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_aftermaths_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_aftermaths_search_path} should return at least one governed prep packet for the aftermaths query")
    workspace_debrief_search_path = f"{workspace_path}?prepQuery=debrief"
    status, body, _, _ = fetch(
        base_url,
        workspace_debrief_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_debrief_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_debrief_search_path)
    require_snippet(body, 'match(es) for "debrief"', workspace_debrief_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_debrief_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_debrief_search_path} should return at least one governed prep packet for the debrief query")
    workspace_debriefs_search_path = f"{workspace_path}?prepQuery=debriefs"
    status, body, _, _ = fetch(
        base_url,
        workspace_debriefs_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_debriefs_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_debriefs_search_path)
    require_snippet(body, 'match(es) for "debriefs"', workspace_debriefs_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_debriefs_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_debriefs_search_path} should return at least one governed prep packet for the debriefs query")
    workspace_debriefing_search_path = f"{workspace_path}?prepQuery=debriefing"
    status, body, _, _ = fetch(
        base_url,
        workspace_debriefing_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_debriefing_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_debriefing_search_path)
    require_snippet(body, 'match(es) for "debriefing"', workspace_debriefing_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_debriefing_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_debriefing_search_path} should return at least one governed prep packet for the debriefing query")
    workspace_debriefings_search_path = f"{workspace_path}?prepQuery=debriefings"
    status, body, _, _ = fetch(
        base_url,
        workspace_debriefings_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_debriefings_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_debriefings_search_path)
    require_snippet(body, 'match(es) for "debriefings"', workspace_debriefings_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_debriefings_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_debriefings_search_path} should return at least one governed prep packet for the debriefings query")
    workspace_postmortem_search_path = f"{workspace_path}?prepQuery=postmortem"
    status, body, _, _ = fetch(
        base_url,
        workspace_postmortem_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_postmortem_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_postmortem_search_path)
    require_snippet(body, 'match(es) for "postmortem"', workspace_postmortem_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_postmortem_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_postmortem_search_path} should return at least one governed prep packet for the postmortem query")
    workspace_post_mortem_search_path = f"{workspace_path}?prepQuery=post%20mortem"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_mortem_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_mortem_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_mortem_search_path)
    require_snippet(body, 'match(es) for "post mortem"', workspace_post_mortem_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_mortem_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_mortem_search_path} should return at least one governed prep packet for the post mortem query")
    workspace_post_mortem_hyphen_search_path = f"{workspace_path}?prepQuery=post-mortem"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_mortem_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_mortem_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_mortem_hyphen_search_path)
    require_snippet(body, 'match(es) for "post-mortem"', workspace_post_mortem_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_mortem_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_mortem_hyphen_search_path} should return at least one governed prep packet for the post-mortem query")
    workspace_postmortems_search_path = f"{workspace_path}?prepQuery=postmortems"
    status, body, _, _ = fetch(
        base_url,
        workspace_postmortems_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_postmortems_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_postmortems_search_path)
    require_snippet(body, 'match(es) for "postmortems"', workspace_postmortems_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_postmortems_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_postmortems_search_path} should return at least one governed prep packet for the postmortems query")
    workspace_post_mortems_search_path = f"{workspace_path}?prepQuery=post%20mortems"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_mortems_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_mortems_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_mortems_search_path)
    require_snippet(body, 'match(es) for "post mortems"', workspace_post_mortems_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_mortems_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_mortems_search_path} should return at least one governed prep packet for the post mortems query")
    workspace_post_mortems_hyphen_search_path = f"{workspace_path}?prepQuery=post-mortems"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_mortems_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_mortems_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_mortems_hyphen_search_path)
    require_snippet(body, 'match(es) for "post-mortems"', workspace_post_mortems_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_mortems_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_mortems_hyphen_search_path} should return at least one governed prep packet for the post-mortems query")
    workspace_postsession_search_path = f"{workspace_path}?prepQuery=postsession"
    status, body, _, _ = fetch(
        base_url,
        workspace_postsession_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_postsession_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_postsession_search_path)
    require_snippet(body, 'match(es) for "postsession"', workspace_postsession_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_postsession_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_postsession_search_path} should return at least one governed prep packet for the postsession query")
    workspace_post_session_search_path = f"{workspace_path}?prepQuery=post%20session"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_session_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_session_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_session_search_path)
    require_snippet(body, 'match(es) for "post session"', workspace_post_session_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_session_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_session_search_path} should return at least one governed prep packet for the post session query")
    workspace_post_session_hyphen_search_path = f"{workspace_path}?prepQuery=post-session"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_session_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_session_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_session_hyphen_search_path)
    require_snippet(body, 'match(es) for "post-session"', workspace_post_session_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_session_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_session_hyphen_search_path} should return at least one governed prep packet for the post-session query")
    workspace_postsessions_search_path = f"{workspace_path}?prepQuery=postsessions"
    status, body, _, _ = fetch(
        base_url,
        workspace_postsessions_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_postsessions_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_postsessions_search_path)
    require_snippet(body, 'match(es) for "postsessions"', workspace_postsessions_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_postsessions_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_postsessions_search_path} should return at least one governed prep packet for the postsessions query")
    workspace_post_sessions_search_path = f"{workspace_path}?prepQuery=post%20sessions"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_sessions_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_sessions_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_sessions_search_path)
    require_snippet(body, 'match(es) for "post sessions"', workspace_post_sessions_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_sessions_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_sessions_search_path} should return at least one governed prep packet for the post sessions query")
    workspace_post_sessions_hyphen_search_path = f"{workspace_path}?prepQuery=post-sessions"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_sessions_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_sessions_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_sessions_hyphen_search_path)
    require_snippet(body, 'match(es) for "post-sessions"', workspace_post_sessions_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_sessions_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_sessions_hyphen_search_path} should return at least one governed prep packet for the post-sessions query")
    workspace_postrun_search_path = f"{workspace_path}?prepQuery=postrun"
    status, body, _, _ = fetch(
        base_url,
        workspace_postrun_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_postrun_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_postrun_search_path)
    require_snippet(body, 'match(es) for "postrun"', workspace_postrun_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_postrun_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_postrun_search_path} should return at least one governed prep packet for the postrun query")
    workspace_post_run_search_path = f"{workspace_path}?prepQuery=post%20run"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_run_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_run_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_run_search_path)
    require_snippet(body, 'match(es) for "post run"', workspace_post_run_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_run_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_run_search_path} should return at least one governed prep packet for the post run query")
    workspace_post_run_hyphen_search_path = f"{workspace_path}?prepQuery=post-run"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_run_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_run_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_run_hyphen_search_path)
    require_snippet(body, 'match(es) for "post-run"', workspace_post_run_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_run_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_run_hyphen_search_path} should return at least one governed prep packet for the post-run query")
    workspace_postruns_search_path = f"{workspace_path}?prepQuery=postruns"
    status, body, _, _ = fetch(
        base_url,
        workspace_postruns_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_postruns_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_postruns_search_path)
    require_snippet(body, 'match(es) for "postruns"', workspace_postruns_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_postruns_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_postruns_search_path} should return at least one governed prep packet for the postruns query")
    workspace_post_runs_search_path = f"{workspace_path}?prepQuery=post%20runs"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_runs_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_runs_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_runs_search_path)
    require_snippet(body, 'match(es) for "post runs"', workspace_post_runs_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_runs_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_runs_search_path} should return at least one governed prep packet for the post runs query")
    workspace_post_runs_hyphen_search_path = f"{workspace_path}?prepQuery=post-runs"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_runs_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_runs_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_runs_hyphen_search_path)
    require_snippet(body, 'match(es) for "post-runs"', workspace_post_runs_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_runs_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_runs_hyphen_search_path} should return at least one governed prep packet for the post-runs query")
    workspace_postgame_search_path = f"{workspace_path}?prepQuery=postgame"
    status, body, _, _ = fetch(
        base_url,
        workspace_postgame_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_postgame_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_postgame_search_path)
    require_snippet(body, 'match(es) for "postgame"', workspace_postgame_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_postgame_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_postgame_search_path} should return at least one governed prep packet for the postgame query")
    workspace_postgames_search_path = f"{workspace_path}?prepQuery=postgames"
    status, body, _, _ = fetch(
        base_url,
        workspace_postgames_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_postgames_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_postgames_search_path)
    require_snippet(body, 'match(es) for "postgames"', workspace_postgames_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_postgames_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_postgames_search_path} should return at least one governed prep packet for the postgames query")
    workspace_post_game_search_path = f"{workspace_path}?prepQuery=post%20game"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_game_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_game_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_game_search_path)
    require_snippet(body, 'match(es) for "post game"', workspace_post_game_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_game_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_game_search_path} should return at least one governed prep packet for the post game query")
    workspace_post_games_search_path = f"{workspace_path}?prepQuery=post%20games"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_games_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_games_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_games_search_path)
    require_snippet(body, 'match(es) for "post games"', workspace_post_games_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_games_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_games_search_path} should return at least one governed prep packet for the post games query")
    workspace_post_game_hyphen_search_path = f"{workspace_path}?prepQuery=post-game"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_game_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_game_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_game_hyphen_search_path)
    require_snippet(body, 'match(es) for "post-game"', workspace_post_game_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_game_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_game_hyphen_search_path} should return at least one governed prep packet for the post-game query")
    workspace_post_games_hyphen_search_path = f"{workspace_path}?prepQuery=post-games"
    status, body, _, _ = fetch(
        base_url,
        workspace_post_games_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_post_games_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_post_games_hyphen_search_path)
    require_snippet(body, 'match(es) for "post-games"', workspace_post_games_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_post_games_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_post_games_hyphen_search_path} should return at least one governed prep packet for the post-games query")
    workspace_recap_search_path = f"{workspace_path}?prepQuery=recap"
    status, body, _, _ = fetch(
        base_url,
        workspace_recap_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_recap_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_recap_search_path)
    require_snippet(body, 'match(es) for "recap"', workspace_recap_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_recap_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_recap_search_path} should return at least one governed prep packet for the recap query")
    workspace_recaps_search_path = f"{workspace_path}?prepQuery=recaps"
    status, body, _, _ = fetch(
        base_url,
        workspace_recaps_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_recaps_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_recaps_search_path)
    require_snippet(body, 'match(es) for "recaps"', workspace_recaps_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_recaps_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_recaps_search_path} should return at least one governed prep packet for the recaps query")
    workspace_aar_search_path = f"{workspace_path}?prepQuery=aar"
    status, body, _, _ = fetch(
        base_url,
        workspace_aar_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_aar_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_aar_search_path)
    require_snippet(body, 'match(es) for "aar"', workspace_aar_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_aar_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_aar_search_path} should return at least one governed prep packet for the aar query")
    workspace_aars_search_path = f"{workspace_path}?prepQuery=aars"
    status, body, _, _ = fetch(
        base_url,
        workspace_aars_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_aars_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_aars_search_path)
    require_snippet(body, 'match(es) for "aars"', workspace_aars_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_aars_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_aars_search_path} should return at least one governed prep packet for the aars query")
    workspace_retro_search_path = f"{workspace_path}?prepQuery=retro"
    status, body, _, _ = fetch(
        base_url,
        workspace_retro_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_retro_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_retro_search_path)
    require_snippet(body, 'match(es) for "retro"', workspace_retro_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_retro_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_retro_search_path} should return at least one governed prep packet for the retro query")
    workspace_retros_search_path = f"{workspace_path}?prepQuery=retros"
    status, body, _, _ = fetch(
        base_url,
        workspace_retros_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_retros_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_retros_search_path)
    require_snippet(body, 'match(es) for "retros"', workspace_retros_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_retros_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_retros_search_path} should return at least one governed prep packet for the retros query")
    workspace_retrospective_search_path = f"{workspace_path}?prepQuery=retrospective"
    status, body, _, _ = fetch(
        base_url,
        workspace_retrospective_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_retrospective_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_retrospective_search_path)
    require_snippet(body, 'match(es) for "retrospective"', workspace_retrospective_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_retrospective_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_retrospective_search_path} should return at least one governed prep packet for the retrospective query")
    workspace_retrospectives_search_path = f"{workspace_path}?prepQuery=retrospectives"
    status, body, _, _ = fetch(
        base_url,
        workspace_retrospectives_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_retrospectives_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_retrospectives_search_path)
    require_snippet(body, 'match(es) for "retrospectives"', workspace_retrospectives_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_retrospectives_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_retrospectives_search_path} should return at least one governed prep packet for the retrospectives query")
    workspace_hotwash_search_path = f"{workspace_path}?prepQuery=hotwash"
    status, body, _, _ = fetch(
        base_url,
        workspace_hotwash_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_hotwash_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_hotwash_search_path)
    require_snippet(body, 'match(es) for "hotwash"', workspace_hotwash_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_hotwash_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_hotwash_search_path} should return at least one governed prep packet for the hotwash query")
    workspace_hotwashes_search_path = f"{workspace_path}?prepQuery=hotwashes"
    status, body, _, _ = fetch(
        base_url,
        workspace_hotwashes_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_hotwashes_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_hotwashes_search_path)
    require_snippet(body, 'match(es) for "hotwashes"', workspace_hotwashes_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_hotwashes_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_hotwashes_search_path} should return at least one governed prep packet for the hotwashes query")
    workspace_hot_wash_search_path = f"{workspace_path}?prepQuery=hot%20wash"
    status, body, _, _ = fetch(
        base_url,
        workspace_hot_wash_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_hot_wash_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_hot_wash_search_path)
    require_snippet(body, 'match(es) for "hot wash"', workspace_hot_wash_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_hot_wash_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_hot_wash_search_path} should return at least one governed prep packet for the hot wash query")
    workspace_hot_washes_search_path = f"{workspace_path}?prepQuery=hot%20washes"
    status, body, _, _ = fetch(
        base_url,
        workspace_hot_washes_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_hot_washes_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_hot_washes_search_path)
    require_snippet(body, 'match(es) for "hot washes"', workspace_hot_washes_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_hot_washes_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_hot_washes_search_path} should return at least one governed prep packet for the hot washes query")
    workspace_hot_wash_hyphen_search_path = f"{workspace_path}?prepQuery=hot-wash"
    status, body, _, _ = fetch(
        base_url,
        workspace_hot_wash_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_hot_wash_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_hot_wash_hyphen_search_path)
    require_snippet(body, 'match(es) for "hot-wash"', workspace_hot_wash_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_hot_wash_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_hot_wash_hyphen_search_path} should return at least one governed prep packet for the hot-wash query")
    workspace_hot_washes_hyphen_search_path = f"{workspace_path}?prepQuery=hot-washes"
    status, body, _, _ = fetch(
        base_url,
        workspace_hot_washes_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_hot_washes_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_hot_washes_hyphen_search_path)
    require_snippet(body, 'match(es) for "hot-washes"', workspace_hot_washes_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_hot_washes_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_hot_washes_hyphen_search_path} should return at least one governed prep packet for the hot-washes query")
    workspace_lessonlearned_search_path = f"{workspace_path}?prepQuery=lessonlearned"
    status, body, _, _ = fetch(
        base_url,
        workspace_lessonlearned_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_lessonlearned_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_lessonlearned_search_path)
    require_snippet(body, 'match(es) for "lessonlearned"', workspace_lessonlearned_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_lessonlearned_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_lessonlearned_search_path} should return at least one governed prep packet for the lessonlearned query")
    workspace_lessonslearned_search_path = f"{workspace_path}?prepQuery=lessonslearned"
    status, body, _, _ = fetch(
        base_url,
        workspace_lessonslearned_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_lessonslearned_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_lessonslearned_search_path)
    require_snippet(body, 'match(es) for "lessonslearned"', workspace_lessonslearned_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_lessonslearned_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_lessonslearned_search_path} should return at least one governed prep packet for the lessonslearned query")
    workspace_lessonlearnt_search_path = f"{workspace_path}?prepQuery=lessonlearnt"
    status, body, _, _ = fetch(
        base_url,
        workspace_lessonlearnt_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_lessonlearnt_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_lessonlearnt_search_path)
    require_snippet(body, 'match(es) for "lessonlearnt"', workspace_lessonlearnt_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_lessonlearnt_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_lessonlearnt_search_path} should return at least one governed prep packet for the lessonlearnt query")
    workspace_lessonslearnt_search_path = f"{workspace_path}?prepQuery=lessonslearnt"
    status, body, _, _ = fetch(
        base_url,
        workspace_lessonslearnt_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_lessonslearnt_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_lessonslearnt_search_path)
    require_snippet(body, 'match(es) for "lessonslearnt"', workspace_lessonslearnt_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_lessonslearnt_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_lessonslearnt_search_path} should return at least one governed prep packet for the lessonslearnt query")
    workspace_lesson_learned_search_path = f"{workspace_path}?prepQuery=lesson%20learned"
    status, body, _, _ = fetch(
        base_url,
        workspace_lesson_learned_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_lesson_learned_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_lesson_learned_search_path)
    require_snippet(body, 'match(es) for "lesson learned"', workspace_lesson_learned_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_lesson_learned_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_lesson_learned_search_path} should return at least one governed prep packet for the lesson learned query")
    workspace_lessons_learned_search_path = f"{workspace_path}?prepQuery=lessons%20learned"
    status, body, _, _ = fetch(
        base_url,
        workspace_lessons_learned_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_lessons_learned_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_lessons_learned_search_path)
    require_snippet(body, 'match(es) for "lessons learned"', workspace_lessons_learned_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_lessons_learned_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_lessons_learned_search_path} should return at least one governed prep packet for the lessons learned query")
    workspace_lesson_learnt_search_path = f"{workspace_path}?prepQuery=lesson%20learnt"
    status, body, _, _ = fetch(
        base_url,
        workspace_lesson_learnt_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_lesson_learnt_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_lesson_learnt_search_path)
    require_snippet(body, 'match(es) for "lesson learnt"', workspace_lesson_learnt_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_lesson_learnt_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_lesson_learnt_search_path} should return at least one governed prep packet for the lesson learnt query")
    workspace_lessons_learnt_search_path = f"{workspace_path}?prepQuery=lessons%20learnt"
    status, body, _, _ = fetch(
        base_url,
        workspace_lessons_learnt_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_lessons_learnt_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_lessons_learnt_search_path)
    require_snippet(body, 'match(es) for "lessons learnt"', workspace_lessons_learnt_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_lessons_learnt_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_lessons_learnt_search_path} should return at least one governed prep packet for the lessons learnt query")
    workspace_lesson_learnt_hyphen_search_path = f"{workspace_path}?prepQuery=lesson-learnt"
    status, body, _, _ = fetch(
        base_url,
        workspace_lesson_learnt_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_lesson_learnt_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_lesson_learnt_hyphen_search_path)
    require_snippet(body, 'match(es) for "lesson-learnt"', workspace_lesson_learnt_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_lesson_learnt_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_lesson_learnt_hyphen_search_path} should return at least one governed prep packet for the lesson-learnt query")
    workspace_lessons_learnt_hyphen_search_path = f"{workspace_path}?prepQuery=lessons-learnt"
    status, body, _, _ = fetch(
        base_url,
        workspace_lessons_learnt_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_lessons_learnt_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_lessons_learnt_hyphen_search_path)
    require_snippet(body, 'match(es) for "lessons-learnt"', workspace_lessons_learnt_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_lessons_learnt_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_lessons_learnt_hyphen_search_path} should return at least one governed prep packet for the lessons-learnt query")
    workspace_lesson_learned_hyphen_search_path = f"{workspace_path}?prepQuery=lesson-learned"
    status, body, _, _ = fetch(
        base_url,
        workspace_lesson_learned_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_lesson_learned_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_lesson_learned_hyphen_search_path)
    require_snippet(body, 'match(es) for "lesson-learned"', workspace_lesson_learned_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_lesson_learned_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_lesson_learned_hyphen_search_path} should return at least one governed prep packet for the lesson-learned query")
    workspace_lessons_learned_hyphen_search_path = f"{workspace_path}?prepQuery=lessons-learned"
    status, body, _, _ = fetch(
        base_url,
        workspace_lessons_learned_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_lessons_learned_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_lessons_learned_hyphen_search_path)
    require_snippet(body, 'match(es) for "lessons-learned"', workspace_lessons_learned_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_lessons_learned_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_lessons_learned_hyphen_search_path} should return at least one governed prep packet for the lessons-learned query")
    workspace_afteraction_search_path = f"{workspace_path}?prepQuery=afteraction"
    status, body, _, _ = fetch(
        base_url,
        workspace_afteraction_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_afteraction_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_afteraction_search_path)
    require_snippet(body, 'match(es) for "afteraction"', workspace_afteraction_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_afteraction_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_afteraction_search_path} should return at least one governed prep packet for the afteraction query")
    workspace_afteractions_search_path = f"{workspace_path}?prepQuery=afteractions"
    status, body, _, _ = fetch(
        base_url,
        workspace_afteractions_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_afteractions_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_afteractions_search_path)
    require_snippet(body, 'match(es) for "afteractions"', workspace_afteractions_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_afteractions_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_afteractions_search_path} should return at least one governed prep packet for the afteractions query")
    workspace_afteractionreport_search_path = f"{workspace_path}?prepQuery=afteractionreport"
    status, body, _, _ = fetch(
        base_url,
        workspace_afteractionreport_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_afteractionreport_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_afteractionreport_search_path)
    require_snippet(body, 'match(es) for "afteractionreport"', workspace_afteractionreport_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_afteractionreport_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_afteractionreport_search_path} should return at least one governed prep packet for the afteractionreport query")
    workspace_afteractionreports_search_path = f"{workspace_path}?prepQuery=afteractionreports"
    status, body, _, _ = fetch(
        base_url,
        workspace_afteractionreports_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_afteractionreports_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_afteractionreports_search_path)
    require_snippet(body, 'match(es) for "afteractionreports"', workspace_afteractionreports_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_afteractionreports_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_afteractionreports_search_path} should return at least one governed prep packet for the afteractionreports query")
    workspace_afteractionreview_search_path = f"{workspace_path}?prepQuery=afteractionreview"
    status, body, _, _ = fetch(
        base_url,
        workspace_afteractionreview_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_afteractionreview_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_afteractionreview_search_path)
    require_snippet(body, 'match(es) for "afteractionreview"', workspace_afteractionreview_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_afteractionreview_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_afteractionreview_search_path} should return at least one governed prep packet for the afteractionreview query")
    workspace_afteractionreviews_search_path = f"{workspace_path}?prepQuery=afteractionreviews"
    status, body, _, _ = fetch(
        base_url,
        workspace_afteractionreviews_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_afteractionreviews_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_afteractionreviews_search_path)
    require_snippet(body, 'match(es) for "afteractionreviews"', workspace_afteractionreviews_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_afteractionreviews_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_afteractionreviews_search_path} should return at least one governed prep packet for the afteractionreviews query")
    workspace_after_action_search_path = f"{workspace_path}?prepQuery=after%20action"
    status, body, _, _ = fetch(
        base_url,
        workspace_after_action_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_after_action_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_after_action_search_path)
    require_snippet(body, 'match(es) for "after action"', workspace_after_action_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_after_action_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_after_action_search_path} should return at least one governed prep packet for the after action query")
    workspace_after_actions_search_path = f"{workspace_path}?prepQuery=after%20actions"
    status, body, _, _ = fetch(
        base_url,
        workspace_after_actions_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_after_actions_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_after_actions_search_path)
    require_snippet(body, 'match(es) for "after actions"', workspace_after_actions_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_after_actions_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_after_actions_search_path} should return at least one governed prep packet for the after actions query")
    workspace_after_action_report_search_path = f"{workspace_path}?prepQuery=after%20action%20report"
    status, body, _, _ = fetch(
        base_url,
        workspace_after_action_report_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_after_action_report_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_after_action_report_search_path)
    require_snippet(body, 'match(es) for "after action report"', workspace_after_action_report_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_after_action_report_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_after_action_report_search_path} should return at least one governed prep packet for the after action report query")
    workspace_after_action_reports_search_path = f"{workspace_path}?prepQuery=after%20action%20reports"
    status, body, _, _ = fetch(
        base_url,
        workspace_after_action_reports_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_after_action_reports_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_after_action_reports_search_path)
    require_snippet(body, 'match(es) for "after action reports"', workspace_after_action_reports_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_after_action_reports_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_after_action_reports_search_path} should return at least one governed prep packet for the after action reports query")
    workspace_after_action_review_search_path = f"{workspace_path}?prepQuery=after%20action%20review"
    status, body, _, _ = fetch(
        base_url,
        workspace_after_action_review_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_after_action_review_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_after_action_review_search_path)
    require_snippet(body, 'match(es) for "after action review"', workspace_after_action_review_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_after_action_review_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_after_action_review_search_path} should return at least one governed prep packet for the after action review query")
    workspace_after_action_reviews_search_path = f"{workspace_path}?prepQuery=after%20action%20reviews"
    status, body, _, _ = fetch(
        base_url,
        workspace_after_action_reviews_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_after_action_reviews_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_after_action_reviews_search_path)
    require_snippet(body, 'match(es) for "after action reviews"', workspace_after_action_reviews_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_after_action_reviews_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_after_action_reviews_search_path} should return at least one governed prep packet for the after action reviews query")
    workspace_after_action_hyphen_search_path = f"{workspace_path}?prepQuery=after-action"
    status, body, _, _ = fetch(
        base_url,
        workspace_after_action_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_after_action_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_after_action_hyphen_search_path)
    require_snippet(body, 'match(es) for "after-action"', workspace_after_action_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_after_action_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_after_action_hyphen_search_path} should return at least one governed prep packet for the after-action query")
    workspace_after_actions_hyphen_search_path = f"{workspace_path}?prepQuery=after-actions"
    status, body, _, _ = fetch(
        base_url,
        workspace_after_actions_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_after_actions_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_after_actions_hyphen_search_path)
    require_snippet(body, 'match(es) for "after-actions"', workspace_after_actions_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_after_actions_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_after_actions_hyphen_search_path} should return at least one governed prep packet for the after-actions query")
    workspace_after_action_report_hyphen_search_path = f"{workspace_path}?prepQuery=after-action%20report"
    status, body, _, _ = fetch(
        base_url,
        workspace_after_action_report_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_after_action_report_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_after_action_report_hyphen_search_path)
    require_snippet(body, 'match(es) for "after-action report"', workspace_after_action_report_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_after_action_report_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_after_action_report_hyphen_search_path} should return at least one governed prep packet for the after-action report query")
    workspace_after_action_reports_hyphen_search_path = f"{workspace_path}?prepQuery=after-action%20reports"
    status, body, _, _ = fetch(
        base_url,
        workspace_after_action_reports_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_after_action_reports_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_after_action_reports_hyphen_search_path)
    require_snippet(body, 'match(es) for "after-action reports"', workspace_after_action_reports_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_after_action_reports_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_after_action_reports_hyphen_search_path} should return at least one governed prep packet for the after-action reports query")
    workspace_after_action_review_hyphen_search_path = f"{workspace_path}?prepQuery=after-action%20review"
    status, body, _, _ = fetch(
        base_url,
        workspace_after_action_review_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_after_action_review_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_after_action_review_hyphen_search_path)
    require_snippet(body, 'match(es) for "after-action review"', workspace_after_action_review_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_after_action_review_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_after_action_review_hyphen_search_path} should return at least one governed prep packet for the after-action review query")
    workspace_after_action_reviews_hyphen_search_path = f"{workspace_path}?prepQuery=after-action%20reviews"
    status, body, _, _ = fetch(
        base_url,
        workspace_after_action_reviews_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_after_action_reviews_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_after_action_reviews_hyphen_search_path)
    require_snippet(body, 'match(es) for "after-action reviews"', workspace_after_action_reviews_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_after_action_reviews_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_after_action_reviews_hyphen_search_path} should return at least one governed prep packet for the after-action reviews query")
    workspace_return_search_path = f"{workspace_path}?prepQuery=return"
    status, body, _, _ = fetch(
        base_url,
        workspace_return_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_return_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_return_search_path)
    require_snippet(body, 'match(es) for "return"', workspace_return_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_return_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_return_search_path} should return at least one governed prep packet for the return query")
    workspace_returns_search_path = f"{workspace_path}?prepQuery=returns"
    status, body, _, _ = fetch(
        base_url,
        workspace_returns_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_returns_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_returns_search_path)
    require_snippet(body, 'match(es) for "returns"', workspace_returns_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_returns_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_returns_search_path} should return at least one governed prep packet for the returns query")
    workspace_return_loop_search_path = f"{workspace_path}?prepQuery=returnloop"
    status, body, _, _ = fetch(
        base_url,
        workspace_return_loop_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_return_loop_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_return_loop_search_path)
    require_snippet(body, 'match(es) for "returnloop"', workspace_return_loop_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_return_loop_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_return_loop_search_path} should return at least one governed prep packet for the returnloop query")
    workspace_return_loops_search_path = f"{workspace_path}?prepQuery=returnloops"
    status, body, _, _ = fetch(
        base_url,
        workspace_return_loops_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_return_loops_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_return_loops_search_path)
    require_snippet(body, 'match(es) for "returnloops"', workspace_return_loops_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_return_loops_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_return_loops_search_path} should return at least one governed prep packet for the returnloops query")
    workspace_next_session_search_path = f"{workspace_path}?prepQuery=nextsession"
    status, body, _, _ = fetch(
        base_url,
        workspace_next_session_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_next_session_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_next_session_search_path)
    require_snippet(body, 'match(es) for "nextsession"', workspace_next_session_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_next_session_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_next_session_search_path} should return at least one governed prep packet for the nextsession query")
    workspace_next_sessions_search_path = f"{workspace_path}?prepQuery=nextsessions"
    status, body, _, _ = fetch(
        base_url,
        workspace_next_sessions_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_next_sessions_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_next_sessions_search_path)
    require_snippet(body, 'match(es) for "nextsessions"', workspace_next_sessions_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_next_sessions_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_next_sessions_search_path} should return at least one governed prep packet for the nextsessions query")
    workspace_next_session_return_search_path = f"{workspace_path}?prepQuery=nextsessionreturn"
    status, body, _, _ = fetch(
        base_url,
        workspace_next_session_return_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_next_session_return_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_next_session_return_search_path)
    require_snippet(body, 'match(es) for "nextsessionreturn"', workspace_next_session_return_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_next_session_return_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_next_session_return_search_path} should return at least one governed prep packet for the nextsessionreturn query")
    workspace_next_session_returns_search_path = f"{workspace_path}?prepQuery=nextsessionreturns"
    status, body, _, _ = fetch(
        base_url,
        workspace_next_session_returns_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_next_session_returns_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_next_session_returns_search_path)
    require_snippet(body, 'match(es) for "nextsessionreturns"', workspace_next_session_returns_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_next_session_returns_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_next_session_returns_search_path} should return at least one governed prep packet for the nextsessionreturns query")
    workspace_session_return_search_path = f"{workspace_path}?prepQuery=sessionreturn"
    status, body, _, _ = fetch(
        base_url,
        workspace_session_return_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_session_return_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_session_return_search_path)
    require_snippet(body, 'match(es) for "sessionreturn"', workspace_session_return_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_session_return_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_session_return_search_path} should return at least one governed prep packet for the sessionreturn query")
    workspace_session_returns_search_path = f"{workspace_path}?prepQuery=sessionreturns"
    status, body, _, _ = fetch(
        base_url,
        workspace_session_returns_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_session_returns_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_session_returns_search_path)
    require_snippet(body, 'match(es) for "sessionreturns"', workspace_session_returns_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_session_returns_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_session_returns_search_path} should return at least one governed prep packet for the sessionreturns query")
    workspace_memory_search_path = f"{workspace_path}?prepQuery=memory"
    status, body, _, _ = fetch(
        base_url,
        workspace_memory_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_memory_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_memory_search_path)
    require_snippet(body, 'match(es) for "memory"', workspace_memory_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_memory_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_memory_search_path} should return at least one governed prep packet for the memory query")
    workspace_memories_search_path = f"{workspace_path}?prepQuery=memories"
    status, body, _, _ = fetch(
        base_url,
        workspace_memories_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_memories_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_memories_search_path)
    require_snippet(body, 'match(es) for "memories"', workspace_memories_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_memories_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_memories_search_path} should return at least one governed prep packet for the memories query")
    workspace_archive_search_path = f"{workspace_path}?prepQuery=archive"
    status, body, _, _ = fetch(
        base_url,
        workspace_archive_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_archive_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_archive_search_path)
    require_snippet(body, 'match(es) for "archive"', workspace_archive_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_archive_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_archive_search_path} should return at least one governed prep packet for the archive query")
    workspace_archives_search_path = f"{workspace_path}?prepQuery=archives"
    status, body, _, _ = fetch(
        base_url,
        workspace_archives_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_archives_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_archives_search_path)
    require_snippet(body, 'match(es) for "archives"', workspace_archives_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_archives_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_archives_search_path} should return at least one governed prep packet for the archives query")
    workspace_history_search_path = f"{workspace_path}?prepQuery=history"
    status, body, _, _ = fetch(
        base_url,
        workspace_history_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_history_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_history_search_path)
    require_snippet(body, 'match(es) for "history"', workspace_history_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_history_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_history_search_path} should return at least one governed prep packet for the history query")
    workspace_histories_search_path = f"{workspace_path}?prepQuery=histories"
    status, body, _, _ = fetch(
        base_url,
        workspace_histories_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_histories_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_histories_search_path)
    require_snippet(body, 'match(es) for "histories"', workspace_histories_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_histories_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_histories_search_path} should return at least one governed prep packet for the histories query")
    workspace_timeline_search_path = f"{workspace_path}?prepQuery=timeline"
    status, body, _, _ = fetch(
        base_url,
        workspace_timeline_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_timeline_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_timeline_search_path)
    require_snippet(body, 'match(es) for "timeline"', workspace_timeline_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_timeline_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_timeline_search_path} should return at least one governed prep packet for the timeline query")
    workspace_timelines_search_path = f"{workspace_path}?prepQuery=timelines"
    status, body, _, _ = fetch(
        base_url,
        workspace_timelines_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_timelines_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_timelines_search_path)
    require_snippet(body, 'match(es) for "timelines"', workspace_timelines_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_timelines_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_timelines_search_path} should return at least one governed prep packet for the timelines query")
    workspace_ledger_search_path = f"{workspace_path}?prepQuery=ledger"
    status, body, _, _ = fetch(
        base_url,
        workspace_ledger_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_ledger_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_ledger_search_path)
    require_snippet(body, 'match(es) for "ledger"', workspace_ledger_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_ledger_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_ledger_search_path} should return at least one governed prep packet for the ledger query")
    workspace_ledgers_search_path = f"{workspace_path}?prepQuery=ledgers"
    status, body, _, _ = fetch(
        base_url,
        workspace_ledgers_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_ledgers_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_ledgers_search_path)
    require_snippet(body, 'match(es) for "ledgers"', workspace_ledgers_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_ledgers_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_ledgers_search_path} should return at least one governed prep packet for the ledgers query")
    workspace_roster_search_path = f"{workspace_path}?prepQuery=roster"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_search_path)
    require_snippet(body, 'match(es) for "roster"', workspace_roster_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_search_path} should return at least one governed prep packet for the roster query")
    workspace_roster_move_search_path = f"{workspace_path}?prepQuery=rostermove"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_move_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_move_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_move_search_path)
    require_snippet(body, 'match(es) for "rostermove"', workspace_roster_move_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_move_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_move_search_path} should return at least one governed prep packet for the rostermove query")
    workspace_crew_move_search_path = f"{workspace_path}?prepQuery=crewmove"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_move_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_move_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_move_search_path)
    require_snippet(body, 'match(es) for "crewmove"', workspace_crew_move_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_move_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_move_search_path} should return at least one governed prep packet for the crewmove query")
    workspace_crew_moves_search_path = f"{workspace_path}?prepQuery=crewmoves"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_moves_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_moves_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_moves_search_path)
    require_snippet(body, 'match(es) for "crewmoves"', workspace_crew_moves_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_moves_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_moves_search_path} should return at least one governed prep packet for the crewmoves query")
    workspace_crew_swap_search_path = f"{workspace_path}?prepQuery=crewswap"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_swap_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_swap_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_swap_search_path)
    require_snippet(body, 'match(es) for "crewswap"', workspace_crew_swap_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_swap_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_swap_search_path} should return at least one governed prep packet for the crewswap query")
    workspace_crew_swaps_search_path = f"{workspace_path}?prepQuery=crewswaps"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_swaps_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_swaps_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_swaps_search_path)
    require_snippet(body, 'match(es) for "crewswaps"', workspace_crew_swaps_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_swaps_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_swaps_search_path} should return at least one governed prep packet for the crewswaps query")
    workspace_roster_moves_search_path = f"{workspace_path}?prepQuery=rostermoves"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_moves_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_moves_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_moves_search_path)
    require_snippet(body, 'match(es) for "rostermoves"', workspace_roster_moves_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_moves_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_moves_search_path} should return at least one governed prep packet for the rostermoves query")
    workspace_roster_swap_search_path = f"{workspace_path}?prepQuery=rosterswap"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_swap_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_swap_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_swap_search_path)
    require_snippet(body, 'match(es) for "rosterswap"', workspace_roster_swap_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_swap_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_swap_search_path} should return at least one governed prep packet for the rosterswap query")
    workspace_roster_swaps_search_path = f"{workspace_path}?prepQuery=rosterswaps"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_swaps_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_swaps_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_swaps_search_path)
    require_snippet(body, 'match(es) for "rosterswaps"', workspace_roster_swaps_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_swaps_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_swaps_search_path} should return at least one governed prep packet for the rosterswaps query")
    workspace_roster_transfer_search_path = f"{workspace_path}?prepQuery=rostertransfer"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_transfer_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_transfer_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_transfer_search_path)
    require_snippet(body, 'match(es) for "rostertransfer"', workspace_roster_transfer_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_transfer_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_transfer_search_path} should return at least one governed prep packet for the rostertransfer query")
    workspace_roster_transfers_search_path = f"{workspace_path}?prepQuery=rostertransfers"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_transfers_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_transfers_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_transfers_search_path)
    require_snippet(body, 'match(es) for "rostertransfers"', workspace_roster_transfers_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_transfers_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_transfers_search_path} should return at least one governed prep packet for the rostertransfers query")
    workspace_roster_handoff_search_path = f"{workspace_path}?prepQuery=rosterhandoff"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_handoff_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_handoff_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_handoff_search_path)
    require_snippet(body, 'match(es) for "rosterhandoff"', workspace_roster_handoff_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_handoff_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_handoff_search_path} should return at least one governed prep packet for the rosterhandoff query")
    workspace_roster_handoffs_search_path = f"{workspace_path}?prepQuery=rosterhandoffs"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_handoffs_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_handoffs_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_handoffs_search_path)
    require_snippet(body, 'match(es) for "rosterhandoffs"', workspace_roster_handoffs_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_handoffs_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_handoffs_search_path} should return at least one governed prep packet for the rosterhandoffs query")
    workspace_crew_handoff_search_path = f"{workspace_path}?prepQuery=crewhandoff"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_handoff_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_handoff_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_handoff_search_path)
    require_snippet(body, 'match(es) for "crewhandoff"', workspace_crew_handoff_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_handoff_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_handoff_search_path} should return at least one governed prep packet for the crewhandoff query")
    workspace_crew_handoffs_search_path = f"{workspace_path}?prepQuery=crewhandoffs"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_handoffs_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_handoffs_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_handoffs_search_path)
    require_snippet(body, 'match(es) for "crewhandoffs"', workspace_crew_handoffs_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_handoffs_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_handoffs_search_path} should return at least one governed prep packet for the crewhandoffs query")
    workspace_crew_transfer_search_path = f"{workspace_path}?prepQuery=crewtransfer"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_transfer_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_transfer_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_transfer_search_path)
    require_snippet(body, 'match(es) for "crewtransfer"', workspace_crew_transfer_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_transfer_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_transfer_search_path} should return at least one governed prep packet for the crewtransfer query")
    workspace_crew_transfers_search_path = f"{workspace_path}?prepQuery=crewtransfers"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_transfers_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_transfers_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_transfers_search_path)
    require_snippet(body, 'match(es) for "crewtransfers"', workspace_crew_transfers_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_transfers_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_transfers_search_path} should return at least one governed prep packet for the crewtransfers query")
    workspace_crew_transfers_split_search_path = f"{workspace_path}?prepQuery=crew%20transfers"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_transfers_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_transfers_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_transfers_split_search_path)
    require_snippet(body, 'match(es) for "crew transfers"', workspace_crew_transfers_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_transfers_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_transfers_split_search_path} should return at least one governed prep packet for the crew transfers query")
    workspace_crew_transfer_split_search_path = f"{workspace_path}?prepQuery=crew%20transfer"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_transfer_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_transfer_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_transfer_split_search_path)
    require_snippet(body, 'match(es) for "crew transfer"', workspace_crew_transfer_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_transfer_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_transfer_split_search_path} should return at least one governed prep packet for the crew transfer query")
    workspace_crew_handoffs_split_search_path = f"{workspace_path}?prepQuery=crew%20handoffs"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_handoffs_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_handoffs_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_handoffs_split_search_path)
    require_snippet(body, 'match(es) for "crew handoffs"', workspace_crew_handoffs_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_handoffs_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_handoffs_split_search_path} should return at least one governed prep packet for the crew handoffs query")
    workspace_crew_handoff_split_search_path = f"{workspace_path}?prepQuery=crew%20handoff"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_handoff_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_handoff_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_handoff_split_search_path)
    require_snippet(body, 'match(es) for "crew handoff"', workspace_crew_handoff_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_handoff_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_handoff_split_search_path} should return at least one governed prep packet for the crew handoff query")
    workspace_crew_moves_split_search_path = f"{workspace_path}?prepQuery=crew%20moves"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_moves_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_moves_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_moves_split_search_path)
    require_snippet(body, 'match(es) for "crew moves"', workspace_crew_moves_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_moves_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_moves_split_search_path} should return at least one governed prep packet for the crew moves query")
    workspace_crew_move_split_search_path = f"{workspace_path}?prepQuery=crew%20move"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_move_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_move_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_move_split_search_path)
    require_snippet(body, 'match(es) for "crew move"', workspace_crew_move_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_move_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_move_split_search_path} should return at least one governed prep packet for the crew move query")
    workspace_roster_transfers_split_search_path = f"{workspace_path}?prepQuery=roster%20transfers"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_transfers_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_transfers_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_transfers_split_search_path)
    require_snippet(body, 'match(es) for "roster transfers"', workspace_roster_transfers_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_transfers_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_transfers_split_search_path} should return at least one governed prep packet for the roster transfers query")
    workspace_roster_transfer_split_search_path = f"{workspace_path}?prepQuery=roster%20transfer"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_transfer_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_transfer_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_transfer_split_search_path)
    require_snippet(body, 'match(es) for "roster transfer"', workspace_roster_transfer_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_transfer_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_transfer_split_search_path} should return at least one governed prep packet for the roster transfer query")
    workspace_roster_handoffs_split_search_path = f"{workspace_path}?prepQuery=roster%20handoffs"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_handoffs_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_handoffs_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_handoffs_split_search_path)
    require_snippet(body, 'match(es) for "roster handoffs"', workspace_roster_handoffs_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_handoffs_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_handoffs_split_search_path} should return at least one governed prep packet for the roster handoffs query")
    workspace_roster_handoff_split_search_path = f"{workspace_path}?prepQuery=roster%20handoff"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_handoff_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_handoff_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_handoff_split_search_path)
    require_snippet(body, 'match(es) for "roster handoff"', workspace_roster_handoff_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_handoff_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_handoff_split_search_path} should return at least one governed prep packet for the roster handoff query")
    workspace_roster_moves_split_search_path = f"{workspace_path}?prepQuery=roster%20moves"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_moves_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_moves_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_moves_split_search_path)
    require_snippet(body, 'match(es) for "roster moves"', workspace_roster_moves_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_moves_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_moves_split_search_path} should return at least one governed prep packet for the roster moves query")
    workspace_roster_move_split_search_path = f"{workspace_path}?prepQuery=roster%20move"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_move_split_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_move_split_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_move_split_search_path)
    require_snippet(body, 'match(es) for "roster move"', workspace_roster_move_split_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_move_split_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_move_split_search_path} should return at least one governed prep packet for the roster move query")
    workspace_roster_move_hyphen_search_path = f"{workspace_path}?prepQuery=roster-move"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_move_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_move_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_move_hyphen_search_path)
    require_snippet(body, 'match(es) for "roster-move"', workspace_roster_move_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_move_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_move_hyphen_search_path} should return at least one governed prep packet for the roster-move query")
    workspace_crew_move_hyphen_search_path = f"{workspace_path}?prepQuery=crew-move"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_move_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_move_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_move_hyphen_search_path)
    require_snippet(body, 'match(es) for "crew-move"', workspace_crew_move_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_move_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_move_hyphen_search_path} should return at least one governed prep packet for the crew-move query")
    workspace_roster_transfer_hyphen_search_path = f"{workspace_path}?prepQuery=roster-transfer"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_transfer_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_transfer_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_transfer_hyphen_search_path)
    require_snippet(body, 'match(es) for "roster-transfer"', workspace_roster_transfer_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_transfer_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_transfer_hyphen_search_path} should return at least one governed prep packet for the roster-transfer query")
    workspace_crew_transfer_hyphen_search_path = f"{workspace_path}?prepQuery=crew-transfer"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_transfer_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_transfer_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_transfer_hyphen_search_path)
    require_snippet(body, 'match(es) for "crew-transfer"', workspace_crew_transfer_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_transfer_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_transfer_hyphen_search_path} should return at least one governed prep packet for the crew-transfer query")
    workspace_roster_handoff_hyphen_search_path = f"{workspace_path}?prepQuery=roster-handoff"
    status, body, _, _ = fetch(
        base_url,
        workspace_roster_handoff_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_roster_handoff_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_roster_handoff_hyphen_search_path)
    require_snippet(body, 'match(es) for "roster-handoff"', workspace_roster_handoff_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_roster_handoff_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_roster_handoff_hyphen_search_path} should return at least one governed prep packet for the roster-handoff query")
    workspace_crew_handoff_hyphen_search_path = f"{workspace_path}?prepQuery=crew-handoff"
    status, body, _, _ = fetch(
        base_url,
        workspace_crew_handoff_hyphen_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_crew_handoff_hyphen_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_crew_handoff_hyphen_search_path)
    require_snippet(body, 'match(es) for "crew-handoff"', workspace_crew_handoff_hyphen_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_crew_handoff_hyphen_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_crew_handoff_hyphen_search_path} should return at least one governed prep packet for the crew-handoff query")
    workspace_preplaunch_search_path = f"{workspace_path}?prepQuery=preplaunch"
    status, body, _, _ = fetch(
        base_url,
        workspace_preplaunch_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_preplaunch_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_preplaunch_search_path)
    require_snippet(body, 'match(es) for "preplaunch"', workspace_preplaunch_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_preplaunch_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_preplaunch_search_path} should return at least one governed prep packet for the preplaunch query")
    workspace_preplaunches_search_path = f"{workspace_path}?prepQuery=preplaunches"
    status, body, _, _ = fetch(
        base_url,
        workspace_preplaunches_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_preplaunches_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_preplaunches_search_path)
    require_snippet(body, 'match(es) for "preplaunches"', workspace_preplaunches_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_preplaunches_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_preplaunches_search_path} should return at least one governed prep packet for the preplaunches query")
    workspace_travel_prefetch_search_path = f"{workspace_path}?prepQuery=travelprefetch"
    status, body, _, _ = fetch(
        base_url,
        workspace_travel_prefetch_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_travel_prefetch_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_travel_prefetch_search_path)
    require_snippet(body, 'match(es) for "travelprefetch"', workspace_travel_prefetch_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_travel_prefetch_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_travel_prefetch_search_path} should return at least one governed prep packet for the travelprefetch query")
    workspace_travel_prefetches_search_path = f"{workspace_path}?prepQuery=travelprefetches"
    status, body, _, _ = fetch(
        base_url,
        workspace_travel_prefetches_search_path,
        public_host=public_host,
        forwarded_proto=forwarded_proto,
        request_headers={"Cookie": cookie_header},
    )
    if status != 200:
        raise AssertionError(f"{workspace_travel_prefetches_search_path} returned {status}, expected 200")
    require_snippet(body, "Search results:", workspace_travel_prefetches_search_path)
    require_snippet(body, 'match(es) for "travelprefetches"', workspace_travel_prefetches_search_path)
    require_snippet(body, prep_launch["packetTitle"], workspace_travel_prefetches_search_path)
    if "No governed prep packet matched that search yet." in body:
        raise AssertionError(f"{workspace_travel_prefetches_search_path} should return at least one governed prep packet for the travelprefetches query")
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
    require_snippet(body, "Trust ranking", publication_detail_path)
    require_snippet(body, "Discovery", publication_detail_path)
    require_snippet(body, "Discoverable now", publication_detail_path)
    require_snippet(body, "Status", publication_detail_path)
    require_snippet(body, "Open build path for", publication_detail_path)
    public_creator_detail_path = extract_optional_match(
        body,
        r'href="([^"]*/artifacts/(?:publications|creator)/[^"]+)"')
    if public_creator_detail_path:
        status, public_creator_body, _, _ = fetch(
            base_url,
            public_creator_detail_path,
            public_host=public_host,
            forwarded_proto=forwarded_proto,
            request_headers={"Cookie": cookie_header},
        )
        if status != 200:
            raise AssertionError(f"{public_creator_detail_path} returned {status}, expected 200")
        require_creator_publication_body(public_creator_body, public_creator_detail_path)
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
        AuditRoute(
            "/",
            "Create account to get preview",
            required_texts=(
                "Final pool 9",
                "Who can get it now",
                "Release proof",
                "Launch readiness",
                "Adoption health",
                "Closure health",
                "Progress trend",
                "Journey pulse",
                "Provider-route stewardship",
                "Current caution",
                "trust-pulse-trend__point",
                "Open what works today",
                "Open progress"),
            expects_header_count=1),
        AuditRoute(
            "/what-is-chummer",
            "One product for rules truth, living dossiers, and session return.",
            required_texts=(
                "The short answer",
                "A Shadowrun companion with one front door",
                "Between build truth and table continuity",
                "Proof, release, and help stay attached",
                "Players, GMs, and creators on one rules truth",
                "Open what works today",
                "Open downloads",
                "Open the help hub"),
            expects_header_count=1),
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
        AuditRoute("/artifacts", "Current proof surfaces", required_texts=("Preview in progress", "Status guide", "Anyone evaluating the preview", "Governed publication discovery", "Published shared publications", "Compare at a glance", "How live publications differ", "Open public publication"), expects_header_count=1),
        AuditRoute("/artifacts/current-preview-build", "Current preview build", required_texts=("Anyone evaluating the preview", "Use and verify this proof", "What this live artifact shows, who it helps, and what to check next", "Start from the live surface", "Open current release", "Open support"), forbidden_texts=(">public<",), expects_header_count=1),
        AuditRoute("/roadmap/nexus-pan", "NEXUS-PAN", required_texts=("Anyone evaluating the preview", "Why this horizon matters now", "Current pain, expected unlock, and the live proof you should compare first", "Compare with current proof", "Need a decision instead?", "Open support"), forbidden_texts=(">public<",), expects_header_count=1),
        AuditRoute(
            "/participate",
            "Choose how to participate",
            required_texts=(
                "Public feedback",
                "Signed-in participation",
                "Report a problem without an account, then stop there unless you want tracked follow-up.",
                "Use the signed-in path when you want a tracked suggestion, beta follow-up, or a bounded contribution flow.",
                "/contact#support-intake",
                "/login?next=/participate/codex",
                "/signup?next=/account/settings",
                "Open guided contribution",
                "Join beta waitlist"),
            expects_header_count=1),
        AuditRoute("/help", "Get help without guessing", required_texts=("Fallback:", "Support, survey, and assistant data stay on a bounded clock", "Who can get it now", "Progress trend", "Adoption health", "trust-pulse-trend__point"), expects_header_count=1),
        AuditRoute(
            "/faq",
            "Plain answers before you spend more time",
            required_texts=(
                "Search the FAQ",
                "Open downloads",
                "Open support intake",
                "See what works today",
                "Still stuck? Open support"),
            expects_header_count=1),
        AuditRoute("/contact", "Open the right support case", expects_header_count=1),
        AuditRoute(
            "/privacy",
            "What Chummer stores, and what it does not",
            required_texts=(
                "Support, survey, and assistant data stay on a bounded clock",
                "What changed in this version",
                "Weekly trust pulse",
                "Open downloads",
                "Open help"),
            expects_header_count=1),
        AuditRoute(
            "/terms",
            "Preview terms in plain language",
            required_texts=(
                "What changed in this version",
                "Open downloads",
                "Open help",
                "Create account to get preview"),
            expects_header_count=1),
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

    status, body, _, _ = fetch(
        args.base_url,
        "/artifacts",
        public_host=args.public_host,
        forwarded_proto=args.forwarded_proto,
    )
    if status != 200:
        raise AssertionError("/artifacts returned a non-200 response while extracting the public creator detail link")

    public_creator_detail_path = extract_first_match(
        body,
        r'href="([^"]*/artifacts/(?:publications|creator)/[^"]+)"',
        "/artifacts",
        "public creator detail link")
    status, public_creator_body, _, _ = fetch(
        args.base_url,
        public_creator_detail_path,
        public_host=args.public_host,
        forwarded_proto=args.forwarded_proto,
    )
    if status != 200:
        raise AssertionError(f"{public_creator_detail_path} returned {status}, expected 200")
    require_creator_publication_body(public_creator_body, public_creator_detail_path)
    print(f"ok {public_creator_detail_path}")

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
