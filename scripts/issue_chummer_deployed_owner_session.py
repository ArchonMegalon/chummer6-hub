#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
from typing import Any

import requests


DEFAULT_COOKIE_NAME = "chummer_hub_access_token"
ENV_KEYS = {
    "IDENTITY_SERVICE_BASE_URL",
    "IDENTITY_ADMIN_KEY",
    "CHUMMER_DEPLOYED_E2E_SUBJECT_ID",
    "CHUMMER_DEPLOYED_E2E_DISPLAY_NAME",
    "CHUMMER_DEPLOYED_E2E_EMAIL",
    "CHUMMER_DEPLOYED_E2E_ROLES",
    "CHUMMER_DEPLOYED_E2E_COOKIE_NAME",
}


class SessionIssueError(RuntimeError):
    pass


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
        if key not in ENV_KEYS or os.environ.get(key):
            continue
        value = raw_value.strip().strip('"').strip("'")
        if value:
            os.environ[key] = value
            loaded[key] = True
        else:
            loaded[key] = False
    return loaded


def required(value: str | None, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SessionIssueError(f"{name} is required")
    return text


def optional(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def roles_from(value: str | None) -> list[str]:
    roles = [role.strip() for role in str(value or "").split(",") if role.strip()]
    return list(dict.fromkeys(roles or ["player"]))


def sha256_text(value: object) -> str:
    text = str(value or "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def issue_session(
    *,
    identity_base_url: str,
    admin_key: str,
    subject_id: str,
    display_name: str | None,
    email: str | None,
    roles: list[str],
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    url = f"{identity_base_url.rstrip('/')}/api/v1/identity/sessions"
    payload = {
        "subjectId": subject_id,
        "displayName": display_name,
        "email": email,
        "requestedRoles": roles,
    }
    response = requests.post(
        url,
        headers={"X-Identity-Admin-Key": admin_key},
        json=payload,
        timeout=timeout_seconds,
    )
    if response.status_code not in {200, 201}:
        detail = response.text[:500] if response.text else ""
        raise SessionIssueError(f"identity session issuance failed: status={response.status_code} detail={detail}")
    try:
        parsed = response.json()
    except ValueError as exc:
        raise SessionIssueError("identity session issuance returned invalid JSON") from exc
    if not isinstance(parsed, dict) or not str(parsed.get("accessToken") or "").strip():
        raise SessionIssueError("identity session issuance returned no accessToken")
    return parsed


def env_line(key: str, value: str) -> str:
    return f"export {key}={shlex.quote(value)}"


def render_output(session: dict[str, Any], output_format: str, cookie_name: str) -> str:
    access_token = required(str(session.get("accessToken") or ""), "accessToken")
    if output_format == "env":
        return "\n".join(
            [
                env_line("CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN", access_token),
                env_line("CHUMMER_DEPLOYED_E2E_AUTH_MODE", "cookie"),
                env_line("CHUMMER_DEPLOYED_E2E_COOKIE_NAME", cookie_name),
            ]
        )
    if output_format == "cookie-header":
        return env_line("CHUMMER_DEPLOYED_E2E_COOKIE_HEADER", f"{cookie_name}={access_token}")
    if output_format == "authorization-header":
        return env_line("CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER", f"Bearer {access_token}")
    if output_format == "summary":
        summary = {
            "status": "issued",
            "subjectId": session.get("subjectId"),
            "sessionId": session.get("sessionId"),
            "roles": session.get("roles", []),
            "expiresAtUtc": session.get("expiresAtUtc"),
            "accessTokenSha256": sha256_text(access_token),
            "rawTokenPrinted": False,
            "nextAction": "Export one of the session env forms before running materialize_origin_dossier_deployed_browser_probe.py.",
        }
        return json.dumps(summary, indent=2, sort_keys=True)
    raise SessionIssueError(f"unsupported output format: {output_format}")


def write_operator_env(path: Path, rendered: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Issue a short-lived Chummer owner session for deployed Origin Edition E2E verification."
    )
    parser.add_argument("--env-file", type=Path, help="Optional operator-local env file with identity admin settings.")
    parser.add_argument("--identity-base-url", default=None)
    parser.add_argument("--admin-key", default=None)
    parser.add_argument("--subject-id", default=None, help="Owner subject id that owns the deployed Origin Dossier publication.")
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--email", default=None)
    parser.add_argument("--roles", default=None, help="Comma-separated roles. Defaults to player.")
    parser.add_argument("--cookie-name", default=None)
    parser.add_argument("--format", choices=("env", "cookie-header", "authorization-header", "summary"), default="env")
    parser.add_argument("--output-env-file", type=Path, help="Write the rendered export lines to an operator-local file with 0600 permissions.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env_file(args.env_file)
    identity_base_url = required(args.identity_base_url or os.environ.get("IDENTITY_SERVICE_BASE_URL"), "IDENTITY_SERVICE_BASE_URL")
    admin_key = required(args.admin_key or os.environ.get("IDENTITY_ADMIN_KEY"), "IDENTITY_ADMIN_KEY")
    subject_id = required(args.subject_id or os.environ.get("CHUMMER_DEPLOYED_E2E_SUBJECT_ID"), "CHUMMER_DEPLOYED_E2E_SUBJECT_ID")
    session = issue_session(
        identity_base_url=identity_base_url,
        admin_key=admin_key,
        subject_id=subject_id,
        display_name=optional(args.display_name or os.environ.get("CHUMMER_DEPLOYED_E2E_DISPLAY_NAME")),
        email=optional(args.email or os.environ.get("CHUMMER_DEPLOYED_E2E_EMAIL")),
        roles=roles_from(args.roles or os.environ.get("CHUMMER_DEPLOYED_E2E_ROLES")),
    )
    rendered = render_output(
        session,
        args.format,
        (args.cookie_name or os.environ.get("CHUMMER_DEPLOYED_E2E_COOKIE_NAME") or DEFAULT_COOKIE_NAME).strip() or DEFAULT_COOKIE_NAME,
    )
    if args.output_env_file is not None:
        write_operator_env(args.output_env_file, rendered)
        print(json.dumps({"status": "written", "path": str(args.output_env_file), "mode": "0600", "rawTokenPrinted": False}, sort_keys=True))
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
