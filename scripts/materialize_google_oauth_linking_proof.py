#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urljoin, urlparse

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from absolute_completion_common import write_json
import google_oauth_linking_evidence_v2 as evidence_v2


RUN_SERVICES_ROOT = SCRIPT_DIR.parents[0]
DEFAULT_BASE_URL = "https://chummer.run"
DEFAULT_OUTPUT_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
DEFAULT_OPERATOR_EVIDENCE_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
DEFAULT_OPERATOR_ASK_TEXT_PATH = RUN_SERVICES_ROOT / "_completion" / "google_oauth_linking" / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"
DEFAULT_OPERATOR_ASK_METADATA_PATH = RUN_SERVICES_ROOT / "_completion" / "google_oauth_linking" / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"
DEFAULT_OPERATOR_EVIDENCE_TEMPLATE_PATH = RUN_SERVICES_ROOT / "_completion" / "google_oauth_linking" / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"
DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT = RUN_SERVICES_ROOT.parent / "_completion" / "telegram_text_delivery"
PROOF_CONTRACT_NAME = evidence_v2.PROOF_CONTRACT_NAME
PROOF_CONTRACT_VERSION = evidence_v2.PROOF_CONTRACT_VERSION
OPERATOR_EVIDENCE_CONTRACT_NAME = evidence_v2.EVIDENCE_CONTRACT_NAME
OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME = evidence_v2.REQUEST_CONTRACT_NAME
GOOGLE_STATE_COOKIE_NAME = "chummer_google_auth_state"
HUB_ACCESS_COOKIE_NAME = "chummer_hub_access_token"
DEFAULT_COOKIE_NAME = HUB_ACCESS_COOKIE_NAME
DEFAULT_AUDIT_EMAIL = "google-oauth-proof@chummer.run"
EMAIL_SIGNIN_PROBE_ENV = "CHUMMER_ENABLE_EMAIL_SIGNIN_PROBE"
AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG = RUN_SERVICES_ROOT / ".state" / "auth_signin_automation_paused.flag"
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
MINIMUM_OPERATOR_SCREENSHOT_COUNT = evidence_v2.MINIMUM_SCREENSHOT_COUNT
REQUIRED_OPERATOR_STEPS = evidence_v2.REQUIRED_OPERATOR_STEPS
DEFAULT_PORTAL_RELEASE_MANIFEST_PATH = evidence_v2.DEFAULT_PORTAL_RELEASE_MANIFEST_PATH
DEFAULT_HUB_RELEASE_MANIFEST_PATH = evidence_v2.DEFAULT_HUB_RELEASE_MANIFEST_PATH
SIGNED_IN_START_NEXT_PATH = "/home"
SIGNED_IN_SETTINGS_PATH = "/account/settings"
SIGNED_IN_GOOGLE_LINK_NEXT_PATH = "/home"
E2E_ENV_KEYS = {
    "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN",
    "CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN",
    "CHUMMER_DEPLOYED_E2E_AUTH_MODE",
    "CHUMMER_DEPLOYED_E2E_COOKIE_NAME",
    "CHUMMER_DEPLOYED_E2E_COOKIE_HEADER",
    "CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER",
}
DEFAULT_OWNER_SESSION_ENV_FILE_CANDIDATES = (
    ".state/deployed-owner-session.fresh.env",
    ".state/deployed-owner-session.env",
    ".env.local",
)
DEFAULT_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("CHUMMER_GOOGLE_OAUTH_PROOF_TIMEOUT_SECONDS", "30"))
DEFAULT_REQUEST_ATTEMPTS = max(1, int(os.environ.get("CHUMMER_GOOGLE_OAUTH_PROOF_ATTEMPTS", "3")))
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36 ChummerGoogleOauthProof/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest().lower()


def google_oauth_request_effective_status(request_status: object, operator_evidence_pass: bool) -> str:
    if operator_evidence_pass:
        return "not_required"
    return "operator_action_required"


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def load_env_file(path: Path | None) -> dict[str, bool]:
    loaded: dict[str, bool] = {}
    if path is None or not path.is_file():
        return loaded
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if key not in E2E_ENV_KEYS or os.environ.get(key):
            continue
        value = raw_value.strip().strip('"').strip("'")
        if value:
            os.environ[key] = value
            loaded[key] = True
        else:
            loaded[key] = False
    return loaded


def resolve_default_owner_session_env_file() -> Path | None:
    for relative_path in DEFAULT_OWNER_SESSION_ENV_FILE_CANDIDATES:
        candidate = RUN_SERVICES_ROOT / relative_path
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw_value = stripped.split("=", 1)
            if key.strip() not in E2E_ENV_KEYS:
                continue
            if raw_value.strip().strip('"').strip("'"):
                return candidate
    return None


def resolve_path(root: Path, candidate: Any) -> Path | None:
    if isinstance(candidate, Path):
        return candidate if candidate.is_absolute() else root / candidate
    if not isinstance(candidate, str):
        return None
    text = candidate.strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else root / path


def telegram_delivery_receipt_details(receipt_name: object) -> dict[str, Any]:
    normalized_receipt_name = str(receipt_name or "").strip()
    receipt_path = DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT / normalized_receipt_name if normalized_receipt_name else None
    receipt_exists = bool(receipt_path and receipt_path.is_file())
    payload = load_json(receipt_path) if receipt_exists and receipt_path is not None else None
    payload = payload if isinstance(payload, dict) else {}
    return {
        "operator_ask_delivery_receipt_path": str(receipt_path) if receipt_path is not None else "",
        "operator_ask_delivery_receipt_exists": receipt_exists,
        "operator_ask_delivery_status": str(payload.get("status") or "").strip(),
        "operator_ask_delivery_generated_at_utc": str(payload.get("generated_at_utc") or "").strip(),
        "operator_ask_delivery_message_ids": list(payload.get("message_ids")) if isinstance(payload.get("message_ids"), list) else [],
        "operator_ask_delivery_text_sha256": str(payload.get("text_sha256") or "").strip(),
        "operator_ask_delivery_text_preview": str(payload.get("text_preview") or "").strip(),
    }


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def is_retryable_request_exception(exc: Exception) -> bool:
    return isinstance(exc, (requests.Timeout, requests.ConnectionError))


def session_request(
    session: requests.Session,
    method: str,
    url: str,
    **kwargs: Any,
) -> requests.Response:
    request_fn = getattr(session, method.lower())
    kwargs.setdefault("timeout", DEFAULT_REQUEST_TIMEOUT_SECONDS)
    for attempt in range(DEFAULT_REQUEST_ATTEMPTS):
        try:
            return request_fn(url, **kwargs)
        except Exception as exc:
            if attempt + 1 >= DEFAULT_REQUEST_ATTEMPTS or not is_retryable_request_exception(exc):
                raise
            time.sleep(min(0.5 * (attempt + 1), 1.5))
    raise RuntimeError("session_request exhausted retry loop unexpectedly")


def auth_mode() -> str:
    mode = os.environ.get("CHUMMER_DEPLOYED_E2E_AUTH_MODE", "cookie").strip().lower()
    return mode if mode in {"cookie", "bearer"} else "cookie"


def email_signin_probe_enabled() -> bool:
    return str(os.environ.get(EMAIL_SIGNIN_PROBE_ENV) or "").strip().lower() in TRUTHY_ENV_VALUES


def auth_signin_automation_pause_note() -> str:
    if not AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG.is_file():
        return ""
    try:
        note = AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        note = ""
    if not note:
        note = "paused by user request"
    return note.splitlines()[0].strip()


def base_url_allows_email_signin_probe(base_url: str) -> bool:
    hostname = (urlparse(base_url).hostname or "").strip().lower()
    if not hostname:
        return False
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def cookie_name() -> str:
    return os.environ.get("CHUMMER_DEPLOYED_E2E_COOKIE_NAME", DEFAULT_COOKIE_NAME).strip() or DEFAULT_COOKIE_NAME


def owner_session_token() -> str:
    return (
        os.environ.get("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "").strip()
        or os.environ.get("CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN", "").strip()
    )


def attach_owner_auth(session: requests.Session, base_url: str) -> tuple[bool, dict[str, Any]]:
    cookie_header = os.environ.get("CHUMMER_DEPLOYED_E2E_COOKIE_HEADER", "").strip()
    authorization_header = os.environ.get("CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER", "").strip()
    if cookie_header:
        session.headers.update({"Cookie": cookie_header})
        return True, {
            "mode": "cookie_header",
            "cookieName": None,
            "tokenSha256": sha256_text(cookie_header),
            "tokenValueStoredInReceipt": False,
        }
    if authorization_header:
        session.headers.update({"Authorization": authorization_header})
        return True, {
            "mode": "authorization_header",
            "cookieName": None,
            "tokenSha256": sha256_text(authorization_header),
            "tokenValueStoredInReceipt": False,
        }

    token = owner_session_token()
    if not token:
        return False, {
            "mode": auth_mode(),
            "cookieName": cookie_name() if auth_mode() == "cookie" else None,
            "tokenSha256": "",
            "tokenValueStoredInReceipt": False,
        }

    mode = auth_mode()
    name = cookie_name()
    if mode == "bearer":
        session.headers.update({"Authorization": f"Bearer {token}"})
    else:
        domain = (urlparse(base_url).hostname or "chummer.run").strip() or "chummer.run"
        session.cookies.set(name, token, domain=domain, path="/")
    return True, {
        "mode": mode,
        "cookieName": name if mode == "cookie" else None,
        "tokenSha256": sha256_text(token),
        "tokenValueStoredInReceipt": False,
    }


def optional_match(pattern: str, body: str) -> str | None:
    match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return unescape(match.group(1)).strip()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract_cookie_value(set_cookie_header: str | None, cookie_name: str) -> str | None:
    if not set_cookie_header:
        return None
    matches = re.findall(rf"{re.escape(cookie_name)}=([^;,\r\n]*)", set_cookie_header)
    for candidate in reversed(matches):
        normalized = candidate.strip()
        if normalized:
            return normalized
    return None


def classify_google_callback_smoke(callback_body: str) -> dict[str, Any]:
    normalized_body = normalize_whitespace(callback_body)
    matched_title = None
    matched_detail = None
    for title in (
        "Google sign-in callback was incomplete",
        "Google sign-in code was malformed",
        "Google sign-in code could not be redeemed",
    ):
        if title in normalized_body:
            matched_title = title
            break

    for detail in (
        "Google did not return an authorization code.",
        "Google returned a malformed authorization code. Start the Google sign-in flow again.",
        "The Google authorization code was rejected. Start a fresh Google sign-in flow and complete it in a single browser window.",
    ):
        if detail in normalized_body:
            matched_detail = detail
            break

    stale_generic_copy_present = (
        "Chummer could not complete the Google sign-in handshake right now. Start the flow again in a moment."
        in normalized_body
        or "Chummer could not complete your Google sign-in right now. Start the flow again in a moment."
        in normalized_body
    )
    return {
        "specific_error_detected": bool(matched_title and matched_detail),
        "matched_title": matched_title,
        "matched_detail": matched_detail,
        "stale_generic_copy_present": stale_generic_copy_present,
    }


def extract_antiforgery_token(body: str) -> str | None:
    return optional_match(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', body)


def extract_inline_callback_url(body: str) -> str | None:
    return optional_match(r'href="([^"]*/auth/email/callback\?[^"]+)"', body)


def extract_google_link_href(body: str) -> str | None:
    return optional_match(r'href="([^"]*/auth/google/link\?[^"]+)"', body)


def extract_google_status_text(body: str) -> str | None:
    return optional_match(r"<span>\s*Google\s*</span>\s*<strong>(.*?)</strong>", body)


def extract_summary_value(body: str, label: str) -> str | None:
    escaped = re.escape(label)
    return optional_match(rf"<span>\s*{escaped}\s*</span>\s*<strong>(.*?)</strong>", body)


def redirect_location_matches_path(location: str | None, expected_path: str) -> bool:
    if not location:
        return False
    return (urlparse(location).path or location).rstrip("/") == expected_path.rstrip("/")


def parse_google_redirect(location: str | None, expected_redirect_uri: str) -> dict[str, Any]:
    if not location:
        return {
            "present": False,
            "is_google_host": False,
            "is_supported_google_path": False,
            "redirect_uri_matches": False,
            "response_type_code": False,
            "scope_includes_openid_profile_email": False,
            "state_present": False,
            "nonce_present": False,
            "code_challenge_present": False,
            "code_challenge_method_s256": False,
            "prompt_select_account": False,
            "pass": False,
            "redirect_target_host": None,
            "redirect_target_path": None,
        }

    parsed = urlparse(location)
    query = parse_qs(parsed.query, keep_blank_values=True)
    scope_tokens = {
        token
        for token in str(query.get("scope", [""])[0]).split()
        if token
    }
    result = {
        "present": True,
        "is_google_host": parsed.hostname == "accounts.google.com",
        "is_supported_google_path": parsed.path in {"/o/oauth2/v2/auth", "/v3/signin/identifier"},
        "redirect_uri_matches": str(query.get("redirect_uri", [""])[0]) == expected_redirect_uri,
        "response_type_code": str(query.get("response_type", [""])[0]) == "code",
        "scope_includes_openid_profile_email": {"openid", "profile", "email"}.issubset(scope_tokens),
        "state_present": bool(str(query.get("state", [""])[0]).strip()),
        "nonce_present": bool(str(query.get("nonce", [""])[0]).strip()),
        "code_challenge_present": bool(str(query.get("code_challenge", [""])[0]).strip()),
        "code_challenge_method_s256": str(query.get("code_challenge_method", [""])[0]) == "S256",
        "prompt_select_account": str(query.get("prompt", [""])[0]) == "select_account",
        "redirect_target_host": parsed.hostname,
        "redirect_target_path": parsed.path,
    }
    result["pass"] = all(
        bool(result[key])
        for key in (
            "is_google_host",
            "is_supported_google_path",
            "redirect_uri_matches",
            "response_type_code",
            "scope_includes_openid_profile_email",
            "state_present",
            "nonce_present",
            "code_challenge_present",
            "code_challenge_method_s256",
            "prompt_select_account",
        )
    )
    return result


def probe_public_google_handoff(base_url: str) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    session = build_session()
    failures: list[str] = []

    login_url = f"{base_url}/login?next=%2Fhome"
    google_start_default_url = f"{base_url}/auth/google/start?next=%2Fhome"

    try:
        login_response = session_request(session, "get", login_url, allow_redirects=False)
        google_href = extract_google_link_href(login_response.text.replace("/auth/google/link", "/auth/google/start")) or optional_match(
            r'href="([^"]*/auth/google/start\?[^"]+)"',
            login_response.text,
        )
    except Exception as exc:
        return {
            "pass": False,
            "failures": [f"login probe failed: {exc}"],
            "login_url": login_url,
            "google_start_url": google_start_default_url,
        }

    if login_response.status_code != 200:
        failures.append(f"/login returned {login_response.status_code}, expected 200")
    if not google_href:
        failures.append("/login did not expose a Google start link")

    google_start_url = urljoin(base_url, google_href or "/auth/google/start?next=/home")
    try:
        google_start_response = session_request(session, "get", google_start_url, allow_redirects=False)
    except Exception as exc:
        return {
            "pass": False,
            "failures": failures + [f"/auth/google/start probe failed: {exc}"],
            "login_url": login_url,
            "google_start_url": google_start_url,
        }

    if google_start_response.status_code not in {302, 303, 307, 308}:
        failures.append(f"/auth/google/start returned {google_start_response.status_code}, expected redirect")

    redirect = parse_google_redirect(
        google_start_response.headers.get("Location"),
        f"{base_url}/auth/google/callback",
    )
    state_cookie_header = google_start_response.headers.get("Set-Cookie", "")
    state_cookie_present = GOOGLE_STATE_COOKIE_NAME in state_cookie_header
    callback_smoke: dict[str, Any] = {
        "pass": False,
        "failures": [],
        "redirect_state_present": False,
        "state_cookie_value_present": False,
        "callback_status": None,
        "specific_error_detected": False,
        "matched_title": None,
        "matched_detail": None,
        "state_cookie_cleared": False,
        "no_store_headers_present": False,
        "stale_generic_copy_present": False,
    }
    if not redirect["pass"]:
        failures.append("/auth/google/start did not produce a complete Google OAuth redirect contract")
    if not state_cookie_present:
        failures.append("/auth/google/start did not issue the Google state cookie")

    callback_redirect_location = google_start_response.headers.get("Location")
    callback_redirect_query = parse_qs(urlparse(callback_redirect_location or "").query, keep_blank_values=True)
    callback_state = str(callback_redirect_query.get("state", [""])[0]).strip()
    callback_redirect_uri = str(callback_redirect_query.get("redirect_uri", [f"{base_url}/auth/google/callback"])[0]).strip() or f"{base_url}/auth/google/callback"
    state_cookie_value = extract_cookie_value(state_cookie_header, GOOGLE_STATE_COOKIE_NAME)
    callback_smoke["redirect_state_present"] = bool(callback_state)
    callback_smoke["state_cookie_value_present"] = bool(state_cookie_value)

    if not callback_state:
        callback_smoke["failures"].append("/auth/google/start did not include a callback state value for the callback smoke check")
    if not state_cookie_value:
        callback_smoke["failures"].append("/auth/google/start did not expose a concrete state cookie value for the callback smoke check")

    if callback_state and state_cookie_value:
        callback_host = urlparse(callback_redirect_uri).hostname or urlparse(base_url).hostname or "chummer.run"
        session.cookies.set(GOOGLE_STATE_COOKIE_NAME, state_cookie_value, domain=callback_host, path="/")
        callback_url = f"{callback_redirect_uri}?state={quote(callback_state, safe='')}"
        try:
            callback_response = session_request(session, "get", callback_url, allow_redirects=False)
        except Exception as exc:
            callback_smoke["failures"].append(f"callback smoke probe failed: {exc}")
        else:
            callback_smoke["callback_status"] = callback_response.status_code
            callback_classification = classify_google_callback_smoke(callback_response.text or "")
            callback_smoke["specific_error_detected"] = callback_classification["specific_error_detected"]
            callback_smoke["matched_title"] = callback_classification["matched_title"]
            callback_smoke["matched_detail"] = callback_classification["matched_detail"]
            callback_smoke["stale_generic_copy_present"] = callback_classification["stale_generic_copy_present"]
            callback_smoke["no_store_headers_present"] = "no-store" in str(callback_response.headers.get("Cache-Control", "")).lower()
            callback_set_cookie = str(callback_response.headers.get("Set-Cookie", "") or "")
            callback_smoke["state_cookie_cleared"] = (
                GOOGLE_STATE_COOKIE_NAME in callback_set_cookie
                and "01 Jan 1970" in callback_set_cookie
            )
            if callback_response.status_code != 200:
                callback_smoke["failures"].append(
                    f"callback smoke returned {callback_response.status_code}, expected 200 auth message page"
                )
            if callback_smoke["specific_error_detected"] is not True:
                callback_smoke["failures"].append(
                    "callback smoke did not return a specific callback failure classification"
                )
            if callback_smoke["stale_generic_copy_present"] is True:
                callback_smoke["failures"].append(
                    "callback smoke still rendered the stale generic Google sign-in failure copy"
                )
            if callback_smoke["state_cookie_cleared"] is not True:
                callback_smoke["failures"].append(
                    "callback smoke did not clear the Google state cookie"
                )
            if callback_smoke["no_store_headers_present"] is not True:
                callback_smoke["failures"].append(
                    "callback smoke response was missing a no-store Cache-Control header"
                )

    callback_smoke["pass"] = not callback_smoke["failures"]
    if callback_smoke["pass"] is not True:
        failures.extend(f"callback_smoke: {item}" for item in callback_smoke["failures"])

    return {
        "pass": not failures,
        "failures": failures,
        "login_url": login_url,
        "google_start_url": google_start_url,
        "login_status": login_response.status_code,
        "google_start_status": google_start_response.status_code,
        "google_start_href_present": bool(google_href),
        "state_cookie_present": state_cookie_present,
        "redirect": redirect,
        "callback_smoke": callback_smoke,
        "covered_assertions": [
            "login page exposes a first-party Google start link",
            "Google start issues a redirect instead of rendering a local dead end",
            "redirect_uri stays on /auth/google/callback",
            "response_type remains code with PKCE S256",
            "scope remains openid profile email",
            "state and nonce are present",
            "prompt stays select_account",
            "callback with a missing code lands on a specific callback failure instead of the stale generic Google sign-in page",
            "callback smoke clears the Google state cookie and stays no-store",
        ],
    }


def evaluate_signed_in_google_link_handoff(
    *,
    base_url: str,
    session: requests.Session,
    email: str,
    login_url: str,
    email_preview_available: bool,
    callback_url: str | None,
    callback_location: str | None,
    session_auth_used: bool,
    session_auth_context: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    home_response = None
    home_google_link_href = None
    try:
        home_response = session_request(session, "get", f"{base_url}{SIGNED_IN_START_NEXT_PATH}", allow_redirects=False)
    except Exception as exc:
        failures.append(f"{SIGNED_IN_START_NEXT_PATH} probe failed: {exc}")
    else:
        if home_response.status_code != 200:
            failures.append(f"{SIGNED_IN_START_NEXT_PATH} returned {home_response.status_code}, expected 200")
        body = home_response.text or ""
        home_google_link_href = extract_google_link_href(body)
        if not home_google_link_href:
            failures.append(f"{SIGNED_IN_START_NEXT_PATH} did not expose the Google link action")

    settings_response = None
    try:
        settings_response = session_request(session, "get", f"{base_url}{SIGNED_IN_SETTINGS_PATH}", allow_redirects=False)
    except Exception as exc:
        failures.append(f"{SIGNED_IN_SETTINGS_PATH} probe failed: {exc}")
    else:
        if settings_response.status_code != 200:
            failures.append(f"{SIGNED_IN_SETTINGS_PATH} returned {settings_response.status_code}, expected 200")
        body = settings_response.text or ""
        for snippet in ("Primary sign-in", "Linked sign-ins", "Linked channels"):
            if snippet not in body:
                failures.append(f"{SIGNED_IN_SETTINGS_PATH} missing required text: {snippet}")

    google_link_response = None
    link_redirect = None
    link_state_cookie_present = False
    google_link_url = f"{base_url}/auth/google/link?next={quote(SIGNED_IN_GOOGLE_LINK_NEXT_PATH, safe='')}"
    try:
        google_link_response = session_request(session, "get", google_link_url, allow_redirects=False)
    except Exception as exc:
        failures.append(f"/auth/google/link probe failed: {exc}")
    else:
        if google_link_response.status_code not in {302, 303, 307, 308}:
            failures.append(f"/auth/google/link returned {google_link_response.status_code}, expected redirect")
        link_state_cookie_present = GOOGLE_STATE_COOKIE_NAME in google_link_response.headers.get("Set-Cookie", "")
        if not link_state_cookie_present:
            failures.append("/auth/google/link did not issue the Google state cookie")
        link_redirect = parse_google_redirect(
            google_link_response.headers.get("Location"),
            f"{base_url}/auth/google/callback",
        )
        if not link_redirect["pass"]:
            failures.append("/auth/google/link did not produce a complete Google OAuth redirect contract")

    status = "pass" if not failures else "fail"
    return {
        "status": status,
        "pass": status == "pass",
        "failures": failures,
        "email": email,
        "login_url": login_url,
        "callback_url": callback_url,
        "callback_redirect_location": callback_location,
        "email_preview_available": email_preview_available,
        "hub_access_cookie_present": HUB_ACCESS_COOKIE_NAME in session.cookies.get_dict(),
        "session_auth_used": session_auth_used,
        "session_auth_context": session_auth_context,
        "home_status": home_response.status_code if home_response is not None else None,
        "settings_status": settings_response.status_code if settings_response is not None else None,
        "account_profile_status": home_response.status_code if home_response is not None else None,
        "account_advanced_status": settings_response.status_code if settings_response is not None else None,
        "google_link_href": home_google_link_href,
        "google_link_status": google_link_response.status_code if google_link_response is not None else None,
        "google_link_state_cookie_present": link_state_cookie_present,
        "google_link_redirect": link_redirect,
        "primary_sign_in_value": extract_summary_value(settings_response.text or "", "Primary sign-in") if settings_response is not None else None,
        "linked_signins_value": extract_summary_value(settings_response.text or "", "Linked sign-ins") if settings_response is not None else None,
        "linked_channels_value": extract_summary_value(settings_response.text or "", "Linked channels") if settings_response is not None else None,
        "primary_auth_value": extract_summary_value(settings_response.text or "", "Primary sign-in") if settings_response is not None else None,
        "linked_identities_value": extract_summary_value(settings_response.text or "", "Linked sign-ins") if settings_response is not None else None,
        "covered_assertions": [
            "email preview can establish a signed-in Hub browser session",
            "signed-in home exposes the Google link action",
            "account settings expose primary sign-in and linked sign-in/channel summaries",
            "auth/google/link performs a provider handoff instead of a dead-end local page",
            "signed-in provider handoff keeps the same Google redirect contract and state cookie",
        ],
    }


def probe_signed_in_google_link_handoff(base_url: str, email: str, *, env_file: Path | None = None) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    load_env_file(env_file or resolve_default_owner_session_env_file())
    session = build_session()
    session_auth_used = False
    has_owner_auth = False
    session_auth_context = {
        "mode": auth_mode(),
        "cookieName": cookie_name() if auth_mode() == "cookie" else None,
        "tokenSha256": "",
        "tokenValueStoredInReceipt": False,
    }

    login_url = f"{base_url}/login?next={quote(SIGNED_IN_START_NEXT_PATH, safe='')}"
    try:
        login_response = session_request(session, "get", login_url, allow_redirects=False)
    except Exception as exc:
        return {
            "pass": False,
            "failures": [f"signed-in login probe failed: {exc}"],
            "login_url": login_url,
            "email": email,
        }

    if login_response.status_code != 200:
        return {
            "status": "fail",
            "pass": False,
            "failures": [f"/login for {SIGNED_IN_START_NEXT_PATH} returned {login_response.status_code}, expected 200"],
            "email": email,
            "login_url": login_url,
            "callback_url": None,
            "callback_redirect_location": None,
            "email_preview_available": False,
            "hub_access_cookie_present": False,
            "session_auth_used": False,
            "session_auth_context": {
                "mode": auth_mode(),
                "cookieName": cookie_name() if auth_mode() == "cookie" else None,
                "tokenSha256": "",
                "tokenValueStoredInReceipt": False,
            },
            "account_profile_status": None,
            "account_advanced_status": None,
            "google_status_text": None,
            "google_link_href": None,
            "google_link_status": None,
            "google_link_state_cookie_present": False,
            "google_link_redirect": None,
            "primary_auth_value": None,
            "linked_identities_value": None,
            "covered_assertions": [
                "The first-party sign-in entry route remains available before provider-specific proof runs.",
            ],
        }

    has_owner_auth, session_auth_context = attach_owner_auth(session, base_url)
    if has_owner_auth:
        return evaluate_signed_in_google_link_handoff(
            base_url=base_url,
            session=session,
            email=email,
            login_url=login_url,
            email_preview_available=False,
            callback_url=None,
            callback_location=None,
            session_auth_used=True,
            session_auth_context=session_auth_context,
        )

    if not email_signin_probe_enabled():
        return {
            "status": "operator_required",
            "pass": False,
            "failures": [],
            "notes": [
                f"Email sign-in probe is disabled by default to avoid sending sign-in emails. Provide a deployed owner session or set {EMAIL_SIGNIN_PROBE_ENV}=1 only when you explicitly want to exercise /auth/email/start on this host.",
                "Final Google account linking still requires browser-backed operator evidence.",
            ],
            "email": email,
            "login_url": login_url,
            "callback_url": None,
            "callback_redirect_location": None,
            "email_preview_available": False,
            "hub_access_cookie_present": False,
            "session_auth_available": False,
            "session_auth_used": session_auth_used,
            "session_auth_context": session_auth_context,
            "account_profile_status": None,
            "account_advanced_status": None,
            "google_status_text": None,
            "google_link_href": None,
            "google_link_status": None,
            "google_link_state_cookie_present": False,
            "google_link_redirect": None,
            "primary_auth_value": None,
            "linked_identities_value": None,
            "covered_assertions": [
                "The first-party sign-in entry route remains available before provider-specific proof runs.",
                "Owner-session-backed proof can validate the signed-in Google link flow without triggering email sign-in traffic.",
                "Final Google account linking still requires browser-backed operator evidence.",
            ],
        }

    if not base_url_allows_email_signin_probe(base_url):
        return {
            "status": "operator_required",
            "pass": False,
            "failures": [],
            "notes": [
                f"Email sign-in probe remains blocked for non-loopback hosts even when {EMAIL_SIGNIN_PROBE_ENV}=1 to avoid sending sign-in emails from shared/public infrastructure. Use a deployed owner session or operator evidence instead.",
                "Final Google account linking still requires browser-backed operator evidence.",
            ],
            "email": email,
            "login_url": login_url,
            "callback_url": None,
            "callback_redirect_location": None,
            "email_preview_available": False,
            "hub_access_cookie_present": False,
            "session_auth_available": False,
            "session_auth_used": session_auth_used,
            "session_auth_context": session_auth_context,
            "account_profile_status": None,
            "account_advanced_status": None,
            "google_status_text": None,
            "google_link_href": None,
            "google_link_status": None,
            "google_link_state_cookie_present": False,
            "google_link_redirect": None,
            "primary_auth_value": None,
            "linked_identities_value": None,
            "covered_assertions": [
                "The first-party sign-in entry route remains available before provider-specific proof runs.",
                "Email sign-in probes are limited to loopback hosts so proof automation cannot trigger public-host sign-in mail.",
                "Final Google account linking still requires browser-backed operator evidence.",
            ],
        }

    antiforgery_token = extract_antiforgery_token(login_response.text)
    if not antiforgery_token:
        return {
            "status": "fail",
            "pass": False,
            "failures": [f"/login for {SIGNED_IN_START_NEXT_PATH} did not expose an antiforgery token"],
            "email": email,
            "login_url": login_url,
            "callback_url": None,
            "callback_redirect_location": None,
            "email_preview_available": False,
            "hub_access_cookie_present": False,
            "session_auth_used": False,
            "session_auth_context": {
                "mode": auth_mode(),
                "cookieName": cookie_name() if auth_mode() == "cookie" else None,
                "tokenSha256": "",
                "tokenValueStoredInReceipt": False,
            },
            "account_profile_status": None,
            "account_advanced_status": None,
            "google_status_text": None,
            "google_link_href": None,
            "google_link_status": None,
            "google_link_state_cookie_present": False,
            "google_link_redirect": None,
            "primary_auth_value": None,
            "linked_identities_value": None,
            "covered_assertions": [
                "The first-party sign-in entry route exposes the normal email sign-in contract before provider-specific proof runs.",
            ],
        }

    callback_url = None
    callback_location = None
    try:
        email_start_response = session_request(
            session,
            "post",
            f"{base_url}/auth/email/start",
            data={
                "__RequestVerificationToken": antiforgery_token,
                "email": email,
                "next": SIGNED_IN_START_NEXT_PATH,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=False,
        )
    except Exception as exc:
        return {
            "status": "fail",
            "pass": False,
            "failures": [f"/auth/email/start failed: {exc}"],
            "email": email,
            "login_url": login_url,
            "callback_url": None,
            "callback_redirect_location": None,
            "email_preview_available": False,
            "hub_access_cookie_present": False,
            "session_auth_used": False,
            "session_auth_context": {
                "mode": auth_mode(),
                "cookieName": cookie_name() if auth_mode() == "cookie" else None,
                "tokenSha256": "",
                "tokenValueStoredInReceipt": False,
            },
            "account_profile_status": None,
            "account_advanced_status": None,
            "google_status_text": None,
            "google_link_href": None,
            "google_link_status": None,
            "google_link_state_cookie_present": False,
            "google_link_redirect": None,
            "primary_auth_value": None,
            "linked_identities_value": None,
            "covered_assertions": [
                "The first-party sign-in flow can begin before provider-specific proof runs.",
            ],
        }

    if email_start_response.status_code != 200:
        return {
            "status": "fail",
            "pass": False,
            "failures": [f"/auth/email/start returned {email_start_response.status_code}, expected 200"],
            "email": email,
            "login_url": login_url,
            "callback_url": None,
            "callback_redirect_location": None,
            "email_preview_available": False,
            "hub_access_cookie_present": False,
            "session_auth_used": False,
            "session_auth_context": {
                "mode": auth_mode(),
                "cookieName": cookie_name() if auth_mode() == "cookie" else None,
                "tokenSha256": "",
                "tokenValueStoredInReceipt": False,
            },
            "account_profile_status": None,
            "account_advanced_status": None,
            "google_status_text": None,
            "google_link_href": None,
            "google_link_status": None,
            "google_link_state_cookie_present": False,
            "google_link_redirect": None,
            "primary_auth_value": None,
            "linked_identities_value": None,
            "covered_assertions": [
                "The first-party email sign-in step can be started before provider-specific proof runs.",
            ],
        }

    callback_candidate = extract_inline_callback_url(email_start_response.text or "")
    if callback_candidate:
        callback_url = urljoin(base_url, callback_candidate)
        try:
            callback_response = session_request(session, "get", callback_url, allow_redirects=False)
        except Exception as exc:
            return {
                "status": "fail",
                "pass": False,
                "failures": [f"/auth/email/callback probe failed: {exc}"],
                "email": email,
                "login_url": login_url,
                "callback_url": callback_url,
                "callback_redirect_location": None,
                "email_preview_available": True,
                "hub_access_cookie_present": HUB_ACCESS_COOKIE_NAME in session.cookies.get_dict(),
                "session_auth_used": False,
                "session_auth_context": {
                    "mode": "inline_email_preview",
                    "cookieName": HUB_ACCESS_COOKIE_NAME,
                    "tokenSha256": "",
                    "tokenValueStoredInReceipt": False,
                },
                "account_profile_status": None,
                "account_advanced_status": None,
                "google_status_text": None,
                "google_link_href": None,
                "google_link_status": None,
                "google_link_state_cookie_present": False,
                "google_link_redirect": None,
                "primary_auth_value": None,
                "linked_identities_value": None,
                "covered_assertions": [
                    "Inline preview sign-in can complete the first-party account return before provider-specific proof runs.",
                ],
            }
        if callback_response.status_code not in {301, 302, 303, 307, 308}:
            return {
                "status": "fail",
                "pass": False,
                "failures": [f"/auth/email/callback returned {callback_response.status_code}, expected redirect"],
                "email": email,
                "login_url": login_url,
                "callback_url": callback_url,
                "callback_redirect_location": callback_response.headers.get("Location"),
                "email_preview_available": True,
                "hub_access_cookie_present": HUB_ACCESS_COOKIE_NAME in session.cookies.get_dict(),
                "session_auth_used": False,
                "session_auth_context": {
                    "mode": "inline_email_preview",
                    "cookieName": HUB_ACCESS_COOKIE_NAME,
                    "tokenSha256": "",
                    "tokenValueStoredInReceipt": False,
                },
                "account_profile_status": None,
                "account_advanced_status": None,
                "google_status_text": None,
                "google_link_href": None,
                "google_link_status": None,
                "google_link_state_cookie_present": False,
                "google_link_redirect": None,
                "primary_auth_value": None,
                "linked_identities_value": None,
                "covered_assertions": [
                    "Inline preview sign-in can complete the first-party account return before provider-specific proof runs.",
                ],
            }
        callback_location = callback_response.headers.get("Location")
        if not redirect_location_matches_path(callback_location, SIGNED_IN_START_NEXT_PATH):
            return {
                "status": "fail",
                "pass": False,
                "failures": [f"/auth/email/callback redirected to {callback_location!r}, expected {SIGNED_IN_START_NEXT_PATH}"],
                "email": email,
                "login_url": login_url,
                "callback_url": callback_url,
                "callback_redirect_location": callback_location,
                "email_preview_available": True,
                "hub_access_cookie_present": HUB_ACCESS_COOKIE_NAME in session.cookies.get_dict(),
                "session_auth_used": False,
                "session_auth_context": {
                    "mode": "inline_email_preview",
                    "cookieName": HUB_ACCESS_COOKIE_NAME,
                    "tokenSha256": "",
                    "tokenValueStoredInReceipt": False,
                },
                "account_profile_status": None,
                "account_advanced_status": None,
                "google_status_text": None,
                "google_link_href": None,
                "google_link_status": None,
                "google_link_state_cookie_present": False,
                "google_link_redirect": None,
                "primary_auth_value": None,
                "linked_identities_value": None,
                "covered_assertions": [
                    "Inline preview sign-in returns to the signed-in home surface before provider-specific proof runs.",
                ],
            }
        if HUB_ACCESS_COOKIE_NAME not in session.cookies.get_dict():
            return {
                "status": "fail",
                "pass": False,
                "failures": ["email preview sign-in did not establish the Hub access cookie"],
                "email": email,
                "login_url": login_url,
                "callback_url": callback_url,
                "callback_redirect_location": callback_location,
                "email_preview_available": True,
                "hub_access_cookie_present": False,
                "session_auth_used": False,
                "session_auth_context": {
                    "mode": "inline_email_preview",
                    "cookieName": HUB_ACCESS_COOKIE_NAME,
                    "tokenSha256": "",
                    "tokenValueStoredInReceipt": False,
                },
                "account_profile_status": None,
                "account_advanced_status": None,
                "google_status_text": None,
                "google_link_href": None,
                "google_link_status": None,
                "google_link_state_cookie_present": False,
                "google_link_redirect": None,
                "primary_auth_value": None,
                "linked_identities_value": None,
                "covered_assertions": [
                    "Inline preview sign-in establishes the normal first-party Hub browser cookie before provider-specific proof runs.",
                ],
            }
        return evaluate_signed_in_google_link_handoff(
            base_url=base_url,
            session=session,
            email=email,
            login_url=login_url,
            email_preview_available=True,
            callback_url=callback_url,
            callback_location=callback_location,
            session_auth_used=False,
            session_auth_context={
                "mode": "inline_email_preview",
                "cookieName": HUB_ACCESS_COOKIE_NAME,
                "tokenSha256": "",
                "tokenValueStoredInReceipt": False,
            },
        )

    return {
        "status": "operator_required",
        "pass": False,
        "failures": [],
        "notes": [
            "/auth/email/start did not expose an inline preview callback on this host; signed-in Google link proof must come from operator evidence unless a deployed owner session is supplied for the first-party preflight."
        ],
        "email": email,
        "login_url": login_url,
        "callback_url": None,
        "callback_redirect_location": None,
        "email_preview_available": False,
        "hub_access_cookie_present": False,
        "session_auth_available": False,
        "session_auth_used": False,
        "session_auth_context": session_auth_context,
        "account_profile_status": None,
        "account_advanced_status": None,
        "google_status_text": None,
        "google_link_href": None,
        "google_link_status": None,
        "google_link_state_cookie_present": False,
        "google_link_redirect": None,
        "primary_auth_value": None,
        "linked_identities_value": None,
        "covered_assertions": [
            "If the host exposes an inline preview callback, signed-in Google link automation can validate the first-party home and settings surfaces before provider handoff.",
            "If the host withholds that callback, a deployed owner session can still validate the first-party home and settings surfaces before the provider hop.",
            "Final Google account linking still requires browser-backed operator evidence.",
        ],
    }


def inspect_operator_evidence(base_url: str, operator_evidence_path: Path) -> dict[str, Any]:
    if base_url.rstrip("/") != DEFAULT_BASE_URL:
        return {
            "pass": False,
            "exists": operator_evidence_path.is_file(),
            "path": str(operator_evidence_path),
            "failures": [f"operator evidence base_url must be {DEFAULT_BASE_URL}"],
        }
    _payload, summary, _raw, failures = evidence_v2.verify_evidence_file(
        operator_evidence_path,
        request_path=DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH,
        portal_release_manifest_path=DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
        hub_release_manifest_path=DEFAULT_HUB_RELEASE_MANIFEST_PATH,
    )
    return {
        **summary,
        "pass": not failures,
        "exists": operator_evidence_path.is_file(),
        "path": str(operator_evidence_path),
        "failures": failures,
        "required_steps": list(REQUIRED_OPERATOR_STEPS),
    }


def _resolve_operator_request_path(root: Path, candidate: Any, default_path: Path) -> Path:
    resolved = resolve_path(root, candidate)
    return resolved if resolved is not None else default_path


def inspect_operator_request_artifacts(
    *,
    base_url: str,
    operator_evidence_path: Path,
    request_receipt_path: Path | None = None,
    operator_ask_text_path: Path | None = None,
    operator_ask_metadata_path: Path | None = None,
    operator_evidence_template_path: Path | None = None,
) -> dict[str, Any]:
    request_receipt_path = _resolve_operator_request_path(
        RUN_SERVICES_ROOT,
        request_receipt_path,
        DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH,
    )
    operator_ask_text_path = _resolve_operator_request_path(
        RUN_SERVICES_ROOT,
        operator_ask_text_path,
        DEFAULT_OPERATOR_ASK_TEXT_PATH,
    )
    operator_ask_metadata_path = _resolve_operator_request_path(
        RUN_SERVICES_ROOT,
        operator_ask_metadata_path,
        DEFAULT_OPERATOR_ASK_METADATA_PATH,
    )
    operator_evidence_template_path = _resolve_operator_request_path(
        RUN_SERVICES_ROOT,
        operator_evidence_template_path,
        DEFAULT_OPERATOR_EVIDENCE_TEMPLATE_PATH,
    )
    request_payload = load_json(request_receipt_path)
    request_exists = request_payload is not None
    request_payload = request_payload or {}
    current_operator_evidence = inspect_operator_evidence(base_url, operator_evidence_path)
    request_status = str(request_payload.get("status") or "").strip()
    request_effective_status = google_oauth_request_effective_status(
        request_status,
        current_operator_evidence.get("pass") is True,
    )
    artifact_intake = request_payload.get("artifact_intake") if isinstance(request_payload.get("artifact_intake"), dict) else {}
    resolved_ask_text_path = _resolve_operator_request_path(
        RUN_SERVICES_ROOT,
        request_payload.get("operator_ask_text_path"),
        operator_ask_text_path,
    )
    resolved_ask_metadata_path = _resolve_operator_request_path(
        RUN_SERVICES_ROOT,
        request_payload.get("operator_ask_metadata_path"),
        operator_ask_metadata_path,
    )
    resolved_template_path = _resolve_operator_request_path(
        RUN_SERVICES_ROOT,
        request_payload.get("operator_evidence_template_path") or request_payload.get("template_path"),
        operator_evidence_template_path,
    )
    ask_metadata = load_json(resolved_ask_metadata_path)
    ask_metadata_exists = ask_metadata is not None
    ask_metadata = ask_metadata or {}
    template_payload = load_json(resolved_template_path)
    template_exists = template_payload is not None
    template_payload = template_payload or {}

    failures: list[str] = []
    if not request_exists:
        failures.append(f"missing operator request receipt: {request_receipt_path}")
    else:
        if str(request_payload.get("contract_name") or "").strip() != OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME:
            failures.append("operator request receipt contract_name mismatch")
        if request_status not in {"operator_action_required", "not_required"}:
            failures.append("operator request receipt status is not recognized")
        elif request_status == "operator_action_required" and current_operator_evidence.get("pass") is True:
            failures.append("operator request receipt still says operator_action_required despite valid operator evidence")
        elif request_status == "not_required" and current_operator_evidence.get("pass") is not True:
            failures.append("operator request receipt says not_required without valid operator evidence")
        if str(request_payload.get("base_url") or "").strip() != base_url:
            failures.append("operator request receipt base_url mismatch")
        if _resolve_operator_request_path(
            RUN_SERVICES_ROOT,
            request_payload.get("required_operator_evidence_path"),
            operator_evidence_path,
        ) != operator_evidence_path:
            failures.append("operator request receipt required_operator_evidence_path mismatch")
        required_steps = request_payload.get("required_steps")
        if required_steps != list(REQUIRED_OPERATOR_STEPS):
            failures.append("operator request receipt required_steps mismatch")
        minimum_screenshot_count = int(request_payload.get("minimum_screenshot_count") or 0)
        if minimum_screenshot_count < MINIMUM_OPERATOR_SCREENSHOT_COUNT:
            failures.append("operator request receipt minimum_screenshot_count is too low")
        recommended_screenshot_paths = request_payload.get("recommended_screenshot_paths")
        if not isinstance(recommended_screenshot_paths, list) or len(recommended_screenshot_paths) < MINIMUM_OPERATOR_SCREENSHOT_COUNT:
            failures.append("operator request receipt recommended_screenshot_paths is too short")

    ask_text_exists = resolved_ask_text_path.is_file()
    ask_text = resolved_ask_text_path.read_text(encoding="utf-8") if ask_text_exists else ""
    ask_text_sha256 = sha256_text(ask_text) if ask_text_exists else ""
    if not ask_text_exists:
        failures.append(f"missing operator ask text: {resolved_ask_text_path}")
    else:
        request_sha256 = str(request_payload.get("operator_message_sha256") or "").strip()
        if request_sha256 and request_sha256 != ask_text_sha256:
            failures.append("operator ask text sha256 does not match request receipt")

    if not ask_metadata_exists:
        failures.append(f"missing operator ask metadata: {resolved_ask_metadata_path}")
    else:
        if _resolve_operator_request_path(
            RUN_SERVICES_ROOT,
            ask_metadata.get("request_receipt_path"),
            request_receipt_path,
        ) != request_receipt_path:
            failures.append("operator ask metadata request_receipt_path mismatch")
        if _resolve_operator_request_path(
            RUN_SERVICES_ROOT,
            ask_metadata.get("required_operator_evidence_path"),
            operator_evidence_path,
        ) != operator_evidence_path:
            failures.append("operator ask metadata required_operator_evidence_path mismatch")
        if _resolve_operator_request_path(
            RUN_SERVICES_ROOT,
            ask_metadata.get("operator_ask_text_path") or ask_metadata.get("message_path"),
            resolved_ask_text_path,
        ) != resolved_ask_text_path:
            failures.append("operator ask metadata operator_ask_text_path mismatch")
        if _resolve_operator_request_path(
            RUN_SERVICES_ROOT,
            ask_metadata.get("operator_ask_metadata_path"),
            resolved_ask_metadata_path,
        ) != resolved_ask_metadata_path:
            failures.append("operator ask metadata operator_ask_metadata_path mismatch")
        if _resolve_operator_request_path(
            RUN_SERVICES_ROOT,
            ask_metadata.get("operator_evidence_template_path") or ask_metadata.get("template_path"),
            resolved_template_path,
        ) != resolved_template_path:
            failures.append("operator ask metadata operator_evidence_template_path mismatch")
        metadata_sha256 = str(ask_metadata.get("message_sha256") or "").strip()
        if metadata_sha256 and ask_text_exists and metadata_sha256 != ask_text_sha256:
            failures.append("operator ask metadata message_sha256 mismatch")
        request_send_command = str(request_payload.get("send_command") or "").strip()
        metadata_send_command = str(ask_metadata.get("send_command") or "").strip()
        if request_send_command and metadata_send_command and request_send_command != metadata_send_command:
            failures.append("operator ask metadata send_command mismatch")
        request_receipt_name = str(request_payload.get("receipt_name") or "").strip()
        metadata_receipt_name = str(ask_metadata.get("receipt_name") or "").strip()
        if request_receipt_name and metadata_receipt_name and request_receipt_name != metadata_receipt_name:
            failures.append("operator ask metadata receipt_name mismatch")

    if not template_exists:
        failures.append(f"missing operator evidence template: {resolved_template_path}")
    else:
        if str(template_payload.get("contract_name") or "").strip() != OPERATOR_EVIDENCE_CONTRACT_NAME:
            failures.append("operator evidence template contract_name mismatch")
        if str(template_payload.get("base_url") or "").strip() != base_url:
            failures.append("operator evidence template base_url mismatch")
        if template_payload.get("verified_steps") != list(REQUIRED_OPERATOR_STEPS):
            failures.append("operator evidence template verified_steps mismatch")
        screenshot_paths = template_payload.get("screenshot_paths")
        if not isinstance(screenshot_paths, list) or len(screenshot_paths) < MINIMUM_OPERATOR_SCREENSHOT_COUNT:
            failures.append("operator evidence template screenshot_paths is too short")

    operator_ask_receipt_name = str(
        ask_metadata.get("receipt_name")
        or request_payload.get("receipt_name")
        or ""
    ).strip()
    operator_ask_send_command = str(
        ask_metadata.get("send_command")
        or request_payload.get("send_command")
        or ""
    ).strip()
    operator_ask_message_preview = str(
        ask_metadata.get("message_preview")
        or request_payload.get("operator_message_preview")
        or ""
    ).strip()
    delivery_receipt = telegram_delivery_receipt_details(operator_ask_receipt_name)
    delivery_text_sha256 = str(delivery_receipt.get("operator_ask_delivery_text_sha256") or "").strip()
    delivery_text_comparable = bool(ask_text_sha256 and delivery_text_sha256)
    delivery_matches_current_text = bool(
        delivery_text_comparable and ask_text_sha256 == delivery_text_sha256
    )
    delivery_needs_resend = bool(
        delivery_text_comparable
        and not delivery_matches_current_text
        and request_effective_status != "not_required"
    )

    return {
        "pass": not failures,
        "request_status": request_status,
        "request_effective_status": request_effective_status,
        "operator_action_still_required": request_effective_status == "operator_action_required",
        "request_receipt_path": str(request_receipt_path),
        "request_receipt_exists": request_exists,
        "operator_ask_text_path": str(resolved_ask_text_path),
        "operator_ask_text_exists": ask_text_exists,
        "operator_ask_metadata_path": str(resolved_ask_metadata_path),
        "operator_ask_metadata_exists": ask_metadata_exists,
        "operator_evidence_template_path": str(resolved_template_path),
        "operator_evidence_template_exists": template_exists,
        "required_operator_evidence_path": str(operator_evidence_path),
        "operator_ask_receipt_name": operator_ask_receipt_name,
        "operator_ask_send_command": operator_ask_send_command,
        "operator_ask_resend_command": operator_ask_send_command if delivery_needs_resend else "",
        "operator_ask_message_preview": operator_ask_message_preview,
        "operator_ask_message_sha256": ask_text_sha256 or None,
        "operator_ask_delivery_current_text_comparable": delivery_text_comparable,
        "operator_ask_delivery_matches_current_text": delivery_matches_current_text,
        "operator_ask_delivery_needs_resend": delivery_needs_resend,
        "required_steps": list(REQUIRED_OPERATOR_STEPS),
        "minimum_screenshot_count": MINIMUM_OPERATOR_SCREENSHOT_COUNT,
        "release_version": request_payload.get("release_version") or ask_metadata.get("release_version"),
        "release_channel": request_payload.get("release_channel") or ask_metadata.get("release_channel"),
        "release_supportability_state": request_payload.get("release_supportability_state") or ask_metadata.get("release_supportability_state"),
        "release_rollout_state": request_payload.get("release_rollout_state") or ask_metadata.get("release_rollout_state"),
        "preferred_drop_path": str(
            artifact_intake.get("preferred_drop_path")
            or request_payload.get("preferred_drop_path")
            or ""
        ).strip(),
        "discover_command": str(artifact_intake.get("discover_command") or "").strip(),
        "import_command": str(
            artifact_intake.get("import_command")
            or request_payload.get("import_command")
            or ""
        ).strip(),
        "auto_import_command": str(artifact_intake.get("auto_import_command") or "").strip(),
        "auto_import_watch_command": str(artifact_intake.get("auto_import_watch_command") or "").strip(),
        "post_import_verify_command": str(artifact_intake.get("post_import_verify_command") or "").strip(),
        "post_import_verify_note": str(artifact_intake.get("post_import_verify_note") or "").strip(),
        "post_import_commands": list(artifact_intake.get("post_import_commands")) if isinstance(artifact_intake.get("post_import_commands"), list) else [],
        "expected_artifact_patterns": list(request_payload.get("expected_artifact_patterns")) if isinstance(request_payload.get("expected_artifact_patterns"), list) else [],
        "drop_roots_checked": list(request_payload.get("drop_roots_checked")) if isinstance(request_payload.get("drop_roots_checked"), list) else [],
        **delivery_receipt,
        "failures": failures,
    }


def inspect_operator_request_artifacts(
    *,
    base_url: str,
    operator_evidence_path: Path,
    request_receipt_path: Path | None = None,
    operator_ask_text_path: Path | None = None,
    operator_ask_metadata_path: Path | None = None,
    operator_evidence_template_path: Path | None = None,
) -> dict[str, Any]:
    """Re-read the current v2 request and its non-authoritative handoff files."""

    request_receipt_path = request_receipt_path or DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH
    operator_ask_text_path = operator_ask_text_path or DEFAULT_OPERATOR_ASK_TEXT_PATH
    operator_ask_metadata_path = operator_ask_metadata_path or DEFAULT_OPERATOR_ASK_METADATA_PATH
    operator_evidence_template_path = (
        operator_evidence_template_path or DEFAULT_OPERATOR_EVIDENCE_TEMPLATE_PATH
    )
    request_payload, request_summary, _raw, request_failures = evidence_v2.verify_request_file(
        request_receipt_path,
        portal_release_manifest_path=DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
        hub_release_manifest_path=DEFAULT_HUB_RELEASE_MANIFEST_PATH,
    )
    failures = list(request_failures)
    if base_url.rstrip("/") != DEFAULT_BASE_URL:
        failures.append(f"operator request base_url must be {DEFAULT_BASE_URL}")

    ask_text_exists = operator_ask_text_path.is_file()
    ask_text = operator_ask_text_path.read_text(encoding="utf-8") if ask_text_exists else ""
    ask_text_sha256 = sha256_text(ask_text) if ask_text else ""
    if not ask_text_exists:
        failures.append(f"missing operator ask text: {operator_ask_text_path}")
    elif request_payload.get("operator_message_sha256") != ask_text_sha256:
        failures.append("operator ask text sha256 does not match request receipt")

    ask_metadata = load_json(operator_ask_metadata_path) or {}
    if not ask_metadata:
        failures.append(f"missing operator ask metadata: {operator_ask_metadata_path}")
    elif ask_metadata.get("message_sha256") != ask_text_sha256:
        failures.append("operator ask metadata message_sha256 mismatch")

    template = load_json(operator_evidence_template_path) or {}
    if not template:
        failures.append(f"missing operator evidence template: {operator_evidence_template_path}")
    elif template.get("contract_name") != OPERATOR_EVIDENCE_CONTRACT_NAME:
        failures.append("operator evidence template contract_name mismatch")

    operator_evidence = inspect_operator_evidence(base_url, operator_evidence_path)
    request_status = str(request_payload.get("status") or "missing")
    operator_action_still_required = (
        request_status == "operator_action_required"
        and operator_evidence.get("pass") is not True
    )
    artifact_intake = (
        request_payload.get("artifact_intake")
        if isinstance(request_payload.get("artifact_intake"), dict)
        else {}
    )
    import_argv = artifact_intake.get("import_argv")
    import_argv = import_argv if isinstance(import_argv, list) else []
    draft = (
        request_payload.get("operator_telegram_draft")
        if isinstance(request_payload.get("operator_telegram_draft"), dict)
        else {}
    )
    return {
        "pass": not failures,
        "request_status": request_status,
        "request_effective_status": (
            "satisfied" if operator_evidence.get("pass") is True else request_status
        ),
        "operator_action_still_required": operator_action_still_required,
        "request_receipt_path": str(request_receipt_path),
        "request_receipt_exists": request_receipt_path.is_file(),
        "request_sha256": request_summary.get("request_sha256"),
        "request_nonce": request_summary.get("request_nonce"),
        "request_binding_sha256": request_summary.get("request_binding_sha256"),
        "release_authority": request_summary.get("release") or {},
        "operator_ask_text_path": str(operator_ask_text_path),
        "operator_ask_text_exists": ask_text_exists,
        "operator_ask_metadata_path": str(operator_ask_metadata_path),
        "operator_ask_metadata_exists": bool(ask_metadata),
        "operator_evidence_template_path": str(operator_evidence_template_path),
        "operator_evidence_template_exists": bool(template),
        "required_operator_evidence_path": str(operator_evidence_path),
        "operator_ask_receipt_name": str(request_payload.get("receipt_name") or ""),
        "operator_ask_send_command": str(request_payload.get("send_command") or ""),
        "operator_ask_resend_command": "",
        "operator_ask_delivery_needs_resend": False,
        "preferred_drop_path": str(artifact_intake.get("preferred_drop_path") or ""),
        "import_command": " ".join(str(item) for item in import_argv),
        "post_import_argv_plan": artifact_intake.get("post_import_argv_plan") or [],
        "failures": failures,
    }


def verify_receipt(
    payload: dict[str, Any],
    *,
    require_pass: bool = True,
    allow_operator_evidence_missing: bool = False,
) -> tuple[bool, list[str]]:
    _summary, issues = evidence_v2.verify_proof_payload(
        payload,
        request_path=DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH,
        evidence_path=DEFAULT_OPERATOR_EVIDENCE_PATH,
        portal_release_manifest_path=DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
        hub_release_manifest_path=DEFAULT_HUB_RELEASE_MANIFEST_PATH,
        require_pass=require_pass,
    )
    return not issues, issues


def materialize(
    *,
    base_url: str,
    output_path: Path,
    operator_evidence_path: Path,
    audit_email: str,
    env_file: Path | None = None,
) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    pause_note = auth_signin_automation_pause_note()
    operator_evidence = inspect_operator_evidence(base_url, operator_evidence_path)
    request_artifacts = inspect_operator_request_artifacts(
        base_url=base_url,
        operator_evidence_path=operator_evidence_path,
    )
    proof_bindings, proof_binding_failures = evidence_v2.current_proof_bindings(
        request_path=DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH,
        evidence_path=operator_evidence_path,
        portal_release_manifest_path=DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
        hub_release_manifest_path=DEFAULT_HUB_RELEASE_MANIFEST_PATH,
    )
    rerun_command = f"python3 scripts/materialize_google_oauth_linking_proof.py --base-url {base_url}"
    if pause_note:
        quick_probe = probe_public_google_handoff(base_url)
        operator_evidence_pass = operator_evidence.get("pass") is True
        operator_ask_resend_command = str(request_artifacts.get("operator_ask_resend_command") or "").strip()
        operator_ask_delivery_needs_resend = bool(request_artifacts.get("operator_ask_delivery_needs_resend"))
        signed_in_satisfied_by_operator_evidence = (
            operator_evidence_pass
            and not bool(request_artifacts.get("operator_action_still_required"))
        )
        signed_in_probe_failures: list[str] = []
        signed_in_probe_notes = [
            "Signed-in Google link automation stayed paused by user request, so email preview sign-in did not run.",
        ]
        if signed_in_satisfied_by_operator_evidence:
            signed_in_status = "pass"
            signed_in_probe_notes.append(
                "Current browser-backed operator evidence already covers the signed-in Google link handoff for this base URL."
            )
        else:
            signed_in_status = "operator_required" if request_artifacts.get("pass") is True else "fail"
            signed_in_probe_failures.append(
                "Auth sign-in automation is paused, so the signed-in Google link lane currently relies on the browser-backed operator evidence bundle instead of email preview automation."
            )
        receipt = {
            "contract_name": PROOF_CONTRACT_NAME,
            "proof_contract_version": PROOF_CONTRACT_VERSION,
            "status": "pass" if quick_probe.get("pass") is True and signed_in_satisfied_by_operator_evidence else "fail",
            "generated_at_utc": now_iso(),
            "base_url": base_url,
            "bindings": proof_bindings,
            "verifier": {
                "script": "scripts/materialize_google_oauth_linking_proof.py",
                "command": [
                    "python3",
                    "scripts/materialize_google_oauth_linking_proof.py",
                    "--base-url",
                    base_url,
                    "--output",
                    str(output_path),
                    "--operator-evidence",
                    str(operator_evidence_path),
                ],
            },
            "automation_pause": {
                "paused": True,
                "flag_path": str(AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG),
                "note": pause_note,
            },
            "quick_handoff_probe": quick_probe,
            "signed_in_link_handoff": {
                "status": signed_in_status,
                "pass": signed_in_status == "pass",
                "failures": signed_in_probe_failures,
                "notes": signed_in_probe_notes,
                "email": audit_email,
                "email_preview_available": False,
                "session_auth_used": False,
                "satisfied_by_operator_evidence": signed_in_satisfied_by_operator_evidence,
                "session_auth_context": {
                    "mode": auth_mode(),
                    "cookieName": cookie_name() if auth_mode() == "cookie" else None,
                    "tokenSha256": "",
                    "tokenValueStoredInReceipt": False,
                },
            },
            "operator_end_to_end_evidence": operator_evidence,
            "operator_request_artifacts": request_artifacts,
            "required_operator_steps": list(REQUIRED_OPERATOR_STEPS),
        }
        failures = [f"quick_handoff_probe: {item}" for item in quick_probe.get("failures", [])]
        failures.extend(f"binding: {item}" for item in proof_binding_failures)
        if not operator_evidence_pass:
            failures.extend(f"operator_end_to_end_evidence: {item}" for item in operator_evidence.get("failures", []))
            failures.extend(f"operator_request_artifacts: {item}" for item in request_artifacts.get("failures", []))
            if operator_ask_delivery_needs_resend:
                if operator_ask_resend_command:
                    failures.append(
                        "operator_request_artifacts: operator ask delivery is stale; "
                        f"resend current ask: {operator_ask_resend_command}"
                    )
                else:
                    failures.append(
                        "operator_request_artifacts: operator ask delivery is stale and should be resent"
                    )
            failures.append(
                "auth_signin_automation_paused: "
                f"{pause_note} ({AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG})"
            )

        next_actions: list[str] = []
        if failures:
            if quick_probe.get("pass") is not True:
                next_actions.append(
                    "Keep the quick handoff probe green: /login must expose Google, and /auth/google/start must keep the redirect_uri, PKCE, nonce, and state contract intact."
                )
            if not operator_evidence_pass:
                request_receipt_path = str(request_artifacts.get("request_receipt_path") or DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH)
                operator_ask_text_path = str(request_artifacts.get("operator_ask_text_path") or DEFAULT_OPERATOR_ASK_TEXT_PATH)
                operator_template_path = str(request_artifacts.get("operator_evidence_template_path") or DEFAULT_OPERATOR_EVIDENCE_TEMPLATE_PATH)
                import_command = str(request_artifacts.get("import_command") or "").strip()
                next_actions.extend(
                    [
                        "Auth sign-in automation remains paused by user request. Keep it paused and satisfy the signed-in Google lane with browser-backed operator evidence instead of email preview automation.",
                        f"Refresh or inspect the current operator request receipt at {request_receipt_path}.",
                        f"Use the current operator ask text at {operator_ask_text_path}.",
                        f"Complete the operator evidence template at {operator_template_path}.",
                        f"Capture a real browser-backed Google linking proof receipt at {operator_evidence_path}.",
                        "The operator receipt must confirm these steps: "
                        + ", ".join(REQUIRED_OPERATOR_STEPS)
                        + ".",
                    ]
                )
                if import_command:
                    next_actions.append(
                        f"When the Google OAuth evidence bundle is ready, import it: {import_command}"
                    )
                    next_actions.append(
                        "That --verify import reruns the full intake-request post-import gate chain, not just the first verifier."
                    )
                next_actions.append(
                    f"The operator receipt must include at least {MINIMUM_OPERATOR_SCREENSHOT_COUNT} screenshot paths that exist on disk."
                )
                if operator_ask_delivery_needs_resend:
                    if operator_ask_resend_command:
                        next_actions.insert(
                            2,
                            "Resend the current Google operator ask before waiting for more evidence: "
                            f"{operator_ask_resend_command}",
                        )
                    else:
                        next_actions.insert(
                            2,
                            "Resend the current Google operator ask before waiting for more evidence.",
                        )
            next_actions.append(f"After the relevant fix, rerun: {rerun_command}")

        if not failures:
            summary = (
                "Live Google OAuth proof is green while auth sign-in automation stays paused because the public handoff probe passes and current browser-backed operator evidence covers the signed-in flow."
            )
        elif operator_evidence_pass and quick_probe.get("pass") is not True:
            summary = (
                "Operator-backed Google linking evidence is green, but the public Google handoff preflight is failing against the live host."
            )
        else:
            summary = (
                "Google OAuth proof still needs current browser-backed operator evidence while auth sign-in automation remains paused."
            )
        receipt["failures"] = failures
        receipt["status"] = "fail" if failures else receipt["status"]
        receipt["next_actions"] = next_actions
        receipt["nextActions"] = list(next_actions)
        receipt["summary"] = summary
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(output_path, receipt)
        return receipt

    quick_probe = probe_public_google_handoff(base_url)
    if env_file is None:
        signed_in_probe = probe_signed_in_google_link_handoff(base_url, audit_email)
    else:
        signed_in_probe = probe_signed_in_google_link_handoff(base_url, audit_email, env_file=env_file)
    operator_ask_resend_command = str(request_artifacts.get("operator_ask_resend_command") or "").strip()
    operator_ask_delivery_needs_resend = bool(request_artifacts.get("operator_ask_delivery_needs_resend"))

    failures = (
        [f"quick_handoff_probe: {item}" for item in quick_probe.get("failures", [])]
        + (
            [f"signed_in_link_handoff: {item}" for item in signed_in_probe.get("failures", [])]
            if signed_in_probe.get("status") == "fail"
            else []
        )
        + [f"operator_end_to_end_evidence: {item}" for item in operator_evidence.get("failures", [])]
        + [f"binding: {item}" for item in proof_binding_failures]
    )
    if operator_evidence.get("pass") is not True:
        failures.extend(f"operator_request_artifacts: {item}" for item in request_artifacts.get("failures", []))
        if operator_ask_delivery_needs_resend:
            if operator_ask_resend_command:
                failures.append(
                    "operator_request_artifacts: operator ask delivery is stale; "
                    f"resend current ask: {operator_ask_resend_command}"
                )
            else:
                failures.append(
                    "operator_request_artifacts: operator ask delivery is stale and should be resent"
                )
    status = "pass" if not failures else "fail"
    quick_probe_failed = quick_probe.get("pass") is not True
    signed_in_status = str(signed_in_probe.get("status") or "").strip()
    signed_in_probe_failed = signed_in_status == "fail"
    operator_evidence_pass = operator_evidence.get("pass") is True
    if signed_in_probe.get("status") == "operator_required":
        signed_in_next_action = (
            "This host does not expose the inline email preview callback for automation. Provide a deployed owner session only if you want the first-party signed-in preflight to stay green locally; the final Google link still requires operator evidence."
        )
    elif signed_in_probe.get("session_auth_used") is True:
        signed_in_next_action = (
            "Keep the first-party signed-in link probe green with the deployed owner session lane: /home must expose the Google link action, /account/settings must keep the sign-in summaries readable, and /auth/google/link must still redirect to Google with a fresh state cookie."
        )
    else:
        signed_in_next_action = (
            "Keep the first-party signed-in link probe green: email preview sign-in must still return to /home, /account/settings must keep the sign-in summaries readable, and /auth/google/link must still redirect to Google with a fresh state cookie."
        )

    request_receipt_path = str(request_artifacts.get("request_receipt_path") or DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH)
    operator_ask_text_path = str(request_artifacts.get("operator_ask_text_path") or DEFAULT_OPERATOR_ASK_TEXT_PATH)
    operator_template_path = str(request_artifacts.get("operator_evidence_template_path") or DEFAULT_OPERATOR_EVIDENCE_TEMPLATE_PATH)
    import_command = str(request_artifacts.get("import_command") or "").strip()
    next_actions: list[str] = []
    if status != "pass":
        if quick_probe_failed:
            next_actions.append(
                "Keep the quick handoff probe green: /login must expose Google, and /auth/google/start must keep the redirect_uri, PKCE, nonce, and state contract intact."
            )
        if signed_in_status in {"fail", "operator_required"}:
            next_actions.append(signed_in_next_action)

        if operator_evidence_pass:
            if signed_in_probe_failed:
                next_actions.append(
                    "Operator evidence already passes for this base URL. Refresh the first-party signed-in preflight instead: the deployed owner session or inline preview sign-in must keep /home, /account/settings, and /auth/google/link reachable."
                )
            elif quick_probe_failed:
                next_actions.append(
                    "Operator evidence already passes for this base URL. Repair the public Google handoff probe instead before recapturing any browser evidence."
                )
        else:
            next_actions.extend(
                [
                    f"Refresh or inspect the current operator request receipt at {request_receipt_path}.",
                    f"Use the current operator ask text at {operator_ask_text_path}.",
                    f"Complete the operator evidence template at {operator_template_path}.",
                    f"Capture a real browser-backed Google linking proof receipt at {operator_evidence_path}.",
                    "The operator receipt must confirm these steps: "
                    + ", ".join(REQUIRED_OPERATOR_STEPS)
                    + ".",
                ]
            )
            if import_command:
                next_actions.append(
                    f"When the Google OAuth evidence bundle is ready, import it: {import_command}"
                )
                next_actions.append(
                    "That --verify import reruns the full intake-request post-import gate chain, not just the first verifier."
                )
            next_actions.append(
                f"The operator receipt must include at least {MINIMUM_OPERATOR_SCREENSHOT_COUNT} screenshot paths that exist on disk."
            )
            if operator_ask_delivery_needs_resend:
                if operator_ask_resend_command:
                    next_actions.insert(
                        2,
                        "Resend the current Google operator ask before waiting for more evidence: "
                        f"{operator_ask_resend_command}",
                    )
                else:
                    next_actions.insert(
                        2,
                        "Resend the current Google operator ask before waiting for more evidence.",
                    )
        next_actions.append(f"After the relevant fix, rerun: {rerun_command}")

    if status == "pass":
        summary = "Live Google OAuth proof is green."
    elif operator_evidence_pass and signed_in_probe_failed and not quick_probe_failed:
        summary = (
            "Operator-backed Google linking evidence is green, but the first-party signed-in preflight is failing against the live host."
        )
    elif operator_evidence_pass and quick_probe_failed and not signed_in_probe_failed:
        summary = (
            "Operator-backed Google linking evidence is green, but the public Google handoff preflight is failing against the live host."
        )
    elif operator_evidence_pass and (quick_probe_failed or signed_in_probe_failed):
        summary = (
            "Operator-backed Google linking evidence is green, but first-party Google preflight checks are failing against the live host."
        )
    else:
        summary = (
            "Live Google OAuth proof is not launch-ready yet. Structural handoff may be green, but operator-backed end-to-end provider evidence is still required."
        )

    receipt = {
        "contract_name": PROOF_CONTRACT_NAME,
        "proof_contract_version": PROOF_CONTRACT_VERSION,
        "status": status,
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "bindings": proof_bindings,
        "verifier": {
            "script": "scripts/materialize_google_oauth_linking_proof.py",
            "command": [
                "python3",
                "scripts/materialize_google_oauth_linking_proof.py",
                "--base-url",
                base_url,
                "--output",
                str(output_path),
                "--operator-evidence",
                str(operator_evidence_path),
            ],
        },
        "quick_handoff_probe": quick_probe,
        "signed_in_link_handoff": signed_in_probe,
        "operator_end_to_end_evidence": operator_evidence,
        "operator_request_artifacts": request_artifacts,
        "required_operator_steps": list(REQUIRED_OPERATOR_STEPS),
        "failures": failures,
        "next_actions": next_actions,
        "nextActions": next_actions,
        "summary": summary,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, receipt)
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize a stronger Google OAuth/account-linking proof receipt.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--operator-evidence", type=Path, default=DEFAULT_OPERATOR_EVIDENCE_PATH)
    parser.add_argument("--audit-email", default=DEFAULT_AUDIT_EMAIL)
    parser.add_argument("--env-file", type=Path, help="Optional local env file containing CHUMMER_DEPLOYED_E2E_* session inputs.")
    parser.add_argument(
        "--allow-email-signin-probe",
        action="store_true",
        help=f"Explicitly allow the proof run to exercise /auth/email/start on loopback hosts only. Default is off to avoid sending sign-in emails.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.allow_email_signin_probe:
        os.environ[EMAIL_SIGNIN_PROBE_ENV] = "1"
    receipt = materialize(
        base_url=str(args.base_url).strip() or DEFAULT_BASE_URL,
        output_path=args.output.resolve(),
        operator_evidence_path=args.operator_evidence.resolve(),
        audit_email=str(args.audit_email).strip() or DEFAULT_AUDIT_EMAIL,
        env_file=args.env_file.resolve() if args.env_file else None,
    )
    print(args.output.resolve())
    print(f"google_oauth_linking_proof:{receipt['status']}")
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
