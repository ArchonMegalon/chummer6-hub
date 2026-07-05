#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
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


RUN_SERVICES_ROOT = SCRIPT_DIR.parents[0]
DEFAULT_BASE_URL = "https://chummer.run"
DEFAULT_OUTPUT_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
DEFAULT_OPERATOR_EVIDENCE_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
DEFAULT_OPERATOR_ASK_TEXT_PATH = RUN_SERVICES_ROOT / "_completion" / "google_oauth_linking" / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"
DEFAULT_OPERATOR_ASK_METADATA_PATH = RUN_SERVICES_ROOT / "_completion" / "google_oauth_linking" / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"
DEFAULT_OPERATOR_EVIDENCE_TEMPLATE_PATH = RUN_SERVICES_ROOT / "_completion" / "google_oauth_linking" / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"
DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT = RUN_SERVICES_ROOT.parent / "_completion" / "telegram_text_delivery"
PROOF_CONTRACT_NAME = "chummer.run.google_oauth_linking_proof"
PROOF_CONTRACT_VERSION = 2
OPERATOR_EVIDENCE_CONTRACT_NAME = "chummer.run.google_oauth_linking_operator_evidence.v1"
OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME = "chummer.run.google_oauth_linking_operator_evidence_request.v1"
GOOGLE_STATE_COOKIE_NAME = "chummer_google_auth_state"
HUB_ACCESS_COOKIE_NAME = "chummer_hub_access_token"
DEFAULT_AUDIT_EMAIL = "google-oauth-proof@chummer.run"
MINIMUM_OPERATOR_SCREENSHOT_COUNT = 2
REQUIRED_OPERATOR_STEPS = (
    "google_sign_in_completed_to_signed_in_state",
    "existing_account_linked_google",
    "google_sign_in_returned_to_existing_account",
    "linked_provider_visible_on_account_profile_or_advanced",
)
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


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


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


def optional_match(pattern: str, body: str) -> str | None:
    match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return unescape(match.group(1)).strip()


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
        login_response = session.get(login_url, allow_redirects=False, timeout=30)
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
        google_start_response = session.get(google_start_url, allow_redirects=False, timeout=30)
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
    state_cookie_present = GOOGLE_STATE_COOKIE_NAME in google_start_response.headers.get("Set-Cookie", "")
    if not redirect["pass"]:
        failures.append("/auth/google/start did not produce a complete Google OAuth redirect contract")
    if not state_cookie_present:
        failures.append("/auth/google/start did not issue the Google state cookie")

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
        "covered_assertions": [
            "login page exposes a first-party Google start link",
            "Google start issues a redirect instead of rendering a local dead end",
            "redirect_uri stays on /auth/google/callback",
            "response_type remains code with PKCE S256",
            "scope remains openid profile email",
            "state and nonce are present",
            "prompt stays select_account",
        ],
    }


def probe_signed_in_google_link_handoff(base_url: str, email: str) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    session = build_session()
    failures: list[str] = []

    login_url = f"{base_url}/login?next={quote('/account/profile', safe='')}"
    try:
        login_response = session.get(login_url, allow_redirects=False, timeout=30)
    except Exception as exc:
        return {
            "pass": False,
            "failures": [f"signed-in login probe failed: {exc}"],
            "login_url": login_url,
            "email": email,
        }

    if login_response.status_code != 200:
        failures.append(f"/login for /account/profile returned {login_response.status_code}, expected 200")

    antiforgery_token = extract_antiforgery_token(login_response.text)
    if not antiforgery_token:
        failures.append("/login for /account/profile did not expose an antiforgery token")

    callback_url = None
    email_start_response = None
    if antiforgery_token:
        try:
            email_start_response = session.post(
                f"{base_url}/auth/email/start",
                data={
                    "__RequestVerificationToken": antiforgery_token,
                    "email": email,
                    "next": "/account/profile",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                allow_redirects=False,
                timeout=30,
            )
        except Exception as exc:
            failures.append(f"/auth/email/start failed: {exc}")
        else:
            if email_start_response.status_code != 200:
                failures.append(f"/auth/email/start returned {email_start_response.status_code}, expected 200")
            callback_candidate = extract_inline_callback_url(email_start_response.text or "")
            if not callback_candidate:
                return {
                    "status": "operator_required",
                    "pass": False,
                    "failures": [],
                    "notes": [
                        "/auth/email/start did not expose an inline preview callback on this host; signed-in Google link proof must come from operator evidence."
                    ],
                    "email": email,
                    "login_url": login_url,
                    "callback_url": None,
                    "callback_redirect_location": None,
                    "email_preview_available": False,
                    "hub_access_cookie_present": False,
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
                        "If the host exposes an inline preview callback, signed-in Google link automation can validate the first-party account surfaces before provider handoff.",
                        "If the host withholds that callback, operator evidence must carry the signed-in linking proof.",
                    ],
                }
            else:
                callback_url = urljoin(base_url, callback_candidate)

    callback_response = None
    callback_location = None
    if callback_url:
        try:
            callback_response = session.get(callback_url, allow_redirects=False, timeout=30)
        except Exception as exc:
            failures.append(f"/auth/email/callback probe failed: {exc}")
        else:
            if callback_response.status_code not in {301, 302, 303, 307, 308}:
                failures.append(f"/auth/email/callback returned {callback_response.status_code}, expected redirect")
            callback_location = callback_response.headers.get("Location")
            if not callback_location or not callback_location.endswith("/account/profile"):
                failures.append(f"/auth/email/callback redirected to {callback_location!r}, expected /account/profile")

    access_cookie_present = HUB_ACCESS_COOKIE_NAME in session.cookies.get_dict()
    if not access_cookie_present:
        failures.append("email preview sign-in did not establish the Hub access cookie")

    profile_response = None
    profile_google_status = None
    profile_google_link_href = None
    if access_cookie_present:
        try:
            profile_response = session.get(f"{base_url}/account/profile", allow_redirects=False, timeout=30)
        except Exception as exc:
            failures.append(f"/account/profile probe failed: {exc}")
        else:
            if profile_response.status_code != 200:
                failures.append(f"/account/profile returned {profile_response.status_code}, expected 200")
            body = profile_response.text or ""
            if "Primary sign-in" not in body:
                failures.append("/account/profile is missing the Primary sign-in drawer")
            if "Google" not in body:
                failures.append("/account/profile is missing the Google sign-in row")
            profile_google_link_href = extract_google_link_href(body)
            if not profile_google_link_href:
                failures.append("/account/profile did not expose the Google link action")
            profile_google_status = extract_google_status_text(body)

    advanced_response = None
    if access_cookie_present:
        try:
            advanced_response = session.get(f"{base_url}/account/advanced", allow_redirects=False, timeout=30)
        except Exception as exc:
            failures.append(f"/account/advanced probe failed: {exc}")
        else:
            if advanced_response.status_code != 200:
                failures.append(f"/account/advanced returned {advanced_response.status_code}, expected 200")
            body = advanced_response.text or ""
            for snippet in ("Primary auth", "Linked identities", "Linked channels", "Follow horizons"):
                if snippet not in body:
                    failures.append(f"/account/advanced missing required text: {snippet}")

    google_link_response = None
    link_redirect = None
    link_state_cookie_present = False
    google_link_url = f"{base_url}/auth/google/link?next=%2Faccount%2Fprofile"
    if access_cookie_present:
        try:
            google_link_response = session.get(google_link_url, allow_redirects=False, timeout=30)
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
        "email_preview_available": callback_url is not None,
        "hub_access_cookie_present": access_cookie_present,
        "account_profile_status": profile_response.status_code if profile_response is not None else None,
        "account_advanced_status": advanced_response.status_code if advanced_response is not None else None,
        "google_status_text": profile_google_status,
        "google_link_href": profile_google_link_href,
        "google_link_status": google_link_response.status_code if google_link_response is not None else None,
        "google_link_state_cookie_present": link_state_cookie_present,
        "google_link_redirect": link_redirect,
        "primary_auth_value": extract_summary_value(advanced_response.text or "", "Primary auth") if advanced_response is not None else None,
        "linked_identities_value": extract_summary_value(advanced_response.text or "", "Linked identities") if advanced_response is not None else None,
        "covered_assertions": [
            "email preview can establish a signed-in Hub browser session",
            "signed-in account profile exposes the Google row and link action",
            "signed-in account advanced metadata exposes primary auth and linked identities",
            "auth/google/link performs a provider handoff instead of a dead-end local page",
            "signed-in provider handoff keeps the same Google redirect contract and state cookie",
        ],
    }


def inspect_operator_evidence(base_url: str, operator_evidence_path: Path) -> dict[str, Any]:
    payload = load_json(operator_evidence_path)
    if payload is None:
        return {
            "pass": False,
            "exists": False,
            "path": str(operator_evidence_path),
            "failures": [f"missing operator evidence receipt: {operator_evidence_path}"],
        }

    failures: list[str] = []
    contract_name = str(payload.get("contract_name") or "").strip()
    status = str(payload.get("status") or "").strip().lower()
    proof_base_url = str(payload.get("base_url") or "").strip()
    verified_steps = payload.get("verified_steps")
    screenshot_paths = payload.get("screenshot_paths")
    observed_at = str(payload.get("observed_at_utc") or payload.get("generated_at_utc") or "").strip()

    if contract_name != OPERATOR_EVIDENCE_CONTRACT_NAME:
        failures.append(f"unexpected operator evidence contract: {contract_name or 'missing'}")
    if status != "pass":
        failures.append(f"operator evidence status is {status or 'missing'}, expected pass")
    if proof_base_url != base_url:
        failures.append(f"operator evidence base_url is {proof_base_url or 'missing'}, expected {base_url}")
    if not observed_at:
        failures.append("operator evidence is missing observed_at_utc/generated_at_utc")
    if not isinstance(verified_steps, list):
        failures.append("operator evidence verified_steps is missing")
        verified_step_set: set[str] = set()
    else:
        verified_step_set = {str(step).strip() for step in verified_steps if str(step).strip()}
        missing_steps = [step for step in REQUIRED_OPERATOR_STEPS if step not in verified_step_set]
        if missing_steps:
            failures.append(f"operator evidence missing verified_steps: {', '.join(missing_steps)}")
    if not isinstance(screenshot_paths, list) or len(screenshot_paths) < 2:
        failures.append("operator evidence screenshot_paths is missing or too short")
        resolved_screenshots: list[Path] = []
    else:
        resolved_screenshots = [
            candidate
            for candidate in (resolve_path(RUN_SERVICES_ROOT, value) for value in screenshot_paths)
            if candidate is not None
        ]
        if len(resolved_screenshots) != len(screenshot_paths):
            failures.append("operator evidence screenshot_paths contains invalid entries")
        else:
            missing = [str(path) for path in resolved_screenshots if not path.is_file()]
            if missing:
                failures.append(f"operator evidence screenshots are missing: {', '.join(missing)}")

    return {
        "pass": not failures,
        "exists": True,
        "path": str(operator_evidence_path),
        "contract_name": contract_name,
        "status": status,
        "base_url": proof_base_url,
        "observed_at_utc": observed_at,
        "verified_steps": sorted(verified_step_set),
        "screenshot_paths": [str(path) for path in resolved_screenshots],
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
        request_status = str(request_payload.get("status") or "").strip()
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
        request_send_command = str(
            request_payload.get("operator_ask_send_command")
            or request_payload.get("send_command")
            or ""
        ).strip()
        metadata_send_command = str(
            ask_metadata.get("operator_ask_send_command")
            or ask_metadata.get("send_command")
            or ""
        ).strip()
        if request_send_command and metadata_send_command and request_send_command != metadata_send_command:
            failures.append("operator ask metadata send_command mismatch")
        request_receipt_name = str(
            request_payload.get("operator_ask_receipt_name")
            or request_payload.get("receipt_name")
            or ""
        ).strip()
        metadata_receipt_name = str(
            ask_metadata.get("operator_ask_receipt_name")
            or ask_metadata.get("receipt_name")
            or ""
        ).strip()
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
        ask_metadata.get("operator_ask_receipt_name")
        or ask_metadata.get("receipt_name")
        or request_payload.get("operator_ask_receipt_name")
        or request_payload.get("receipt_name")
        or ""
    ).strip()
    operator_ask_send_command = str(
        ask_metadata.get("operator_ask_send_command")
        or ask_metadata.get("send_command")
        or request_payload.get("operator_ask_send_command")
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
    delivery_needs_resend = bool(delivery_text_comparable and not delivery_matches_current_text)

    return {
        "pass": not failures,
        "request_status": str(request_payload.get("status") or "").strip(),
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
        "post_import_commands": list(artifact_intake.get("post_import_commands")) if isinstance(artifact_intake.get("post_import_commands"), list) else [],
        "expected_artifact_patterns": list(request_payload.get("expected_artifact_patterns")) if isinstance(request_payload.get("expected_artifact_patterns"), list) else [],
        "drop_roots_checked": list(request_payload.get("drop_roots_checked")) if isinstance(request_payload.get("drop_roots_checked"), list) else [],
        **delivery_receipt,
        "failures": failures,
    }


def verify_receipt(
    payload: dict[str, Any],
    *,
    require_pass: bool = True,
    allow_operator_evidence_missing: bool = False,
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if str(payload.get("contract_name") or "").strip() != PROOF_CONTRACT_NAME:
        issues.append("contract_name_mismatch")
    if int(payload.get("proof_contract_version") or 0) < PROOF_CONTRACT_VERSION:
        issues.append("proof_contract_version_too_old")
    if str(payload.get("base_url") or "").strip() != DEFAULT_BASE_URL:
        issues.append("base_url_not_live")

    quick_probe = payload.get("quick_handoff_probe")
    if not isinstance(quick_probe, dict):
        issues.append("missing_quick_handoff_probe")
    else:
        if quick_probe.get("pass") is not True:
            issues.append("quick_handoff_probe_not_pass")

    signed_in_probe = payload.get("signed_in_link_handoff")
    if not isinstance(signed_in_probe, dict):
        issues.append("missing_signed_in_link_handoff")
    else:
        if str(signed_in_probe.get("status") or "").strip() not in {"pass", "operator_required"}:
            issues.append("signed_in_link_handoff_not_pass")

    operator_evidence = payload.get("operator_end_to_end_evidence")
    if not isinstance(operator_evidence, dict):
        issues.append("missing_operator_end_to_end_evidence")
    else:
        if operator_evidence.get("pass") is not True:
            operator_request_artifacts = payload.get("operator_request_artifacts")
            if not isinstance(operator_request_artifacts, dict):
                issues.append("missing_operator_request_artifacts")
            elif operator_request_artifacts.get("pass") is not True:
                issues.append("operator_request_artifacts_not_pass")
            elif not (allow_operator_evidence_missing and not require_pass):
                issues.append("operator_end_to_end_evidence_not_pass")

    if require_pass:
        if str(payload.get("status") or "").strip().lower() != "pass":
            issues.append("receipt_status_not_pass")
        if payload.get("failures"):
            issues.append("receipt_failures_present")

    return not issues, issues


def materialize(
    *,
    base_url: str,
    output_path: Path,
    operator_evidence_path: Path,
    audit_email: str,
) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    quick_probe = probe_public_google_handoff(base_url)
    signed_in_probe = probe_signed_in_google_link_handoff(base_url, audit_email)
    operator_evidence = inspect_operator_evidence(base_url, operator_evidence_path)
    request_artifacts = inspect_operator_request_artifacts(
        base_url=base_url,
        operator_evidence_path=operator_evidence_path,
    )
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
    if signed_in_probe.get("status") == "operator_required":
        signed_in_next_action = (
            "This host does not expose the inline email preview callback for automation, so the signed-in Google link lane must be proven with operator evidence instead of the local helper."
        )
    else:
        signed_in_next_action = (
            "Keep the first-party signed-in link probe green: email preview sign-in must still expose Google linking on /account/profile and /account/advanced, and /auth/google/link must still redirect to Google with a fresh state cookie."
        )

    request_receipt_path = str(request_artifacts.get("request_receipt_path") or DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH)
    operator_ask_text_path = str(request_artifacts.get("operator_ask_text_path") or DEFAULT_OPERATOR_ASK_TEXT_PATH)
    operator_template_path = str(request_artifacts.get("operator_evidence_template_path") or DEFAULT_OPERATOR_EVIDENCE_TEMPLATE_PATH)
    next_actions = [] if status == "pass" else [
        "Keep the quick handoff probe green: /login must expose Google, and /auth/google/start must keep the redirect_uri, PKCE, nonce, and state contract intact.",
        signed_in_next_action,
        f"Refresh or inspect the current operator request receipt at {request_receipt_path}.",
        f"Use the current operator ask text at {operator_ask_text_path}.",
        f"Complete the operator evidence template at {operator_template_path}.",
        f"Capture a real browser-backed Google linking proof receipt at {operator_evidence_path}.",
        "The operator receipt must confirm these steps: "
        + ", ".join(REQUIRED_OPERATOR_STEPS)
        + ".",
        f"The operator receipt must include at least {MINIMUM_OPERATOR_SCREENSHOT_COUNT} screenshot paths that exist on disk.",
        "After the operator evidence exists, rerun: python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run",
    ]
    if status != "pass" and operator_ask_delivery_needs_resend:
        if operator_ask_resend_command:
            next_actions.insert(
                3,
                "Resend the current Google operator ask before waiting for more evidence: "
                f"{operator_ask_resend_command}",
            )
        else:
            next_actions.insert(
                3,
                "Resend the current Google operator ask before waiting for more evidence.",
            )

    receipt = {
        "contract_name": PROOF_CONTRACT_NAME,
        "proof_contract_version": PROOF_CONTRACT_VERSION,
        "status": status,
        "generated_at_utc": now_iso(),
        "base_url": base_url,
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
        "summary": (
            "Live Google OAuth proof is green."
            if status == "pass"
            else "Live Google OAuth proof is not launch-ready yet. Structural handoff may be green, but operator-backed end-to-end provider evidence is still required."
        ),
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = materialize(
        base_url=str(args.base_url).strip() or DEFAULT_BASE_URL,
        output_path=args.output.resolve(),
        operator_evidence_path=args.operator_evidence.resolve(),
        audit_email=str(args.audit_email).strip() or DEFAULT_AUDIT_EMAIL,
    )
    print(args.output.resolve())
    print(f"google_oauth_linking_proof:{receipt['status']}")
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
