#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
OUTPUT_JSON = PUBLISHED_ROOT / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json"
OUTPUT_MD = PUBLISHED_ROOT / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.md"
DEFAULT_RELEASE_UPLOAD_OPERATOR_EMAIL = "tibor.girschele@gmail.com"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def trim_env(name: str) -> str:
    return os.environ.get(name, "").strip()


def truthy_env(name: str) -> bool:
    return trim_env(name).lower() in {"1", "true", "yes", "on"}


def looks_like_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))


def parse_allowed_emails(raw_value: str) -> list[str]:
    return [entry.strip() for entry in raw_value.split(",") if entry.strip()]


def summarize_url(value: str) -> dict[str, object]:
    if not value:
        return {
            "present": False,
            "https": False,
            "origin": None,
            "path": None,
        }

    parsed = urlparse(value)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
    return {
        "present": True,
        "https": parsed.scheme.lower() == "https" and bool(parsed.netloc),
        "origin": origin,
        "path": parsed.path or "/",
    }


def build_payload() -> dict[str, object]:
    failures: list[str] = []

    require_brilliant_directories_checkout = truthy_env("CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT")
    supporter_plan_url = trim_env("BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL")
    member_portal_url = trim_env("BRILLIANT_DIRECTORIES_MEMBER_PORTAL_URL")
    user_id_parameter = trim_env("BRILLIANT_DIRECTORIES_CHECKOUT_USER_ID_PARAMETER")
    email_parameter = trim_env("BRILLIANT_DIRECTORIES_CHECKOUT_EMAIL_PARAMETER")
    plan_parameter = trim_env("BRILLIANT_DIRECTORIES_CHECKOUT_PLAN_PARAMETER")
    configured_allowed_emails_raw = trim_env("CHUMMER_RELEASE_UPLOAD_ALLOWED_EMAILS")
    configured_allowed_emails = parse_allowed_emails(configured_allowed_emails_raw)

    supporter_plan_summary = summarize_url(supporter_plan_url)
    member_portal_summary = summarize_url(member_portal_url)

    if bool(supporter_plan_url) != bool(member_portal_url):
        failures.append("billing handoff config is partial; supporter checkout and member portal must both be set or both be empty")

    if supporter_plan_url and not supporter_plan_summary["https"]:
        failures.append("supporter checkout URL must be an https URL")
    if member_portal_url and not member_portal_summary["https"]:
        failures.append("member portal URL must be an https URL")

    billing_mode = "unavailable"
    if supporter_plan_url or member_portal_url:
        billing_mode = "external_handoff_configured"
        if not user_id_parameter:
            failures.append("billing checkout user-id parameter is missing")
        if not email_parameter:
            failures.append("billing checkout email parameter is missing")
        if not plan_parameter:
            failures.append("billing checkout plan parameter is missing")
    elif require_brilliant_directories_checkout:
        failures.append("billing checkout is required for this release but Brilliant Directories handoff is still unavailable")

    invalid_allowed_emails = [email for email in configured_allowed_emails if not looks_like_email(email)]
    if invalid_allowed_emails:
        failures.append("release-upload allowlist contains invalid email entries")

    release_upload_mode = "default_single_operator"
    effective_release_upload_emails = [DEFAULT_RELEASE_UPLOAD_OPERATOR_EMAIL]
    if configured_allowed_emails:
        release_upload_mode = "configured_allowlist"
        effective_release_upload_emails = configured_allowed_emails
        if not any(
            email.lower() == DEFAULT_RELEASE_UPLOAD_OPERATOR_EMAIL.lower()
            for email in configured_allowed_emails
        ):
            failures.append("release-upload allowlist must include tibor.girschele@gmail.com")

    payload = {
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "verdict": "READY" if not failures else "NOT_READY",
        "failures": failures,
        "billing": {
            "mode": billing_mode,
            "checkout_live_required": require_brilliant_directories_checkout,
            "supporter_plan": supporter_plan_summary,
            "member_portal": member_portal_summary,
            "checkout_parameters": {
                "user_id": user_id_parameter or None,
                "email": email_parameter or None,
                "plan": plan_parameter or None,
            },
        },
        "release_upload": {
            "mode": release_upload_mode,
            "default_operator_email": DEFAULT_RELEASE_UPLOAD_OPERATOR_EMAIL,
            "configured_allowed_email_count": len(configured_allowed_emails),
            "invalid_allowed_email_entries": invalid_allowed_emails,
            "effective_allowed_emails": effective_release_upload_emails,
        },
    }
    return payload


def write_outputs(payload: dict[str, object]) -> None:
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    billing = payload.get("billing") if isinstance(payload.get("billing"), dict) else {}
    release_upload = payload.get("release_upload") if isinstance(payload.get("release_upload"), dict) else {}
    lines = [
        "# Account Handoff Runtime Config",
        "",
        f"- Generated: {payload.get('generated_at_utc')}",
        f"- Status: `{payload.get('status')}`",
        f"- Verdict: `{payload.get('verdict')}`",
        f"- Billing mode: `{billing.get('mode')}`",
        f"- Billing live required: `{billing.get('checkout_live_required')}`",
        f"- Release-upload mode: `{release_upload.get('mode')}`",
        "",
    ]
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    if failures:
        lines.append("## Failures")
        lines.append("")
        lines.extend(f"- {failure}" for failure in failures)
        lines.append("")
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    payload = build_payload()
    write_outputs(payload)
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
