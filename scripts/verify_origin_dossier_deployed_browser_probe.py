#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import hashlib
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_verify_paths import deployed_browser_probe_from_env
from origin_edition_provider_config import origin_owner_url


CONTRACT_NAME = "chummer.origin_edition.deployed_browser_probe.v1"
REQUIRED_PASS_FLAGS = (
    "logged_in_browser_verified",
    "selected_face_cover_visible",
    "read_tab_visible",
    "listen_tab_visible",
    "watch_tab_visible",
    "canon_audit_tab_visible",
    "read_gate_verified",
    "chummer_run_listen_gate_verified",
    "watch_gate_verified",
    "cover_route_verified",
    "book_route_verified",
    "audiobook_share_url_trusted",
    "dossier_share_url_trusted",
    "owner_playback_e2e_verified",
    "unauthenticated_detail_redirect_verified",
    "unauthenticated_read_redirect_verified",
    "unauthenticated_listen_redirect_verified",
    "unauthenticated_book_redirect_verified",
    "unauthenticated_cover_redirect_verified",
    "unauthenticated_video_redirect_verified",
    "all_private_routes_login_protected",
)
PRIVATE_ROUTE_FLAGS = (
    "unauthenticated_detail_redirect_verified",
    "unauthenticated_read_redirect_verified",
    "unauthenticated_listen_redirect_verified",
    "unauthenticated_book_redirect_verified",
    "unauthenticated_cover_redirect_verified",
    "unauthenticated_video_redirect_verified",
    "all_private_routes_login_protected",
)
FORBIDDEN_VALUE_MARKERS = (
    "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN=",
    "Bearer ",
    "Cookie:",
    "secret-token",
    "owner-session-token",
    "super-secret",
    "secret-session",
    "secret-bearer-session",
    "rangersofB5",
    "api:",
    "api.telegram.org/bot",
    "TELEGRAM_BOT_TOKEN=",
    "EA_TELEGRAM_BOT_TOKEN=",
    "UNMIXR_API_KEY=",
    "audiobookshelf_api_token=",
    "telegram_bot_token=",
)


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def sha256_text(value: object) -> str:
    text = str(value or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def verify(path: Path, *, require_pass: bool = False) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not path.is_file():
        return False, [f"missing_deployed_browser_probe:{path}"]
    text = path.read_text(encoding="utf-8")
    for marker in FORBIDDEN_VALUE_MARKERS:
        if marker in text:
            issues.append(f"forbidden_secret_marker:{marker}")
    try:
        payload = read_json(path)
    except (json.JSONDecodeError, ValueError) as exc:
        issues.append(f"invalid_json:{exc.__class__.__name__}")
        return False, issues

    if payload.get("contractName") != CONTRACT_NAME:
        issues.append("contract_name_mismatch")
    status = str(payload.get("status") or "")
    if status not in {"pass", "blocked"}:
        issues.append(f"unexpected_status:{status}")
    if require_pass and status != "pass":
        issues.append("deployed_browser_probe_not_pass")
    passed = status == "pass"
    if not str(payload.get("updated_at") or "").strip():
        issues.append("updated_at_missing")
    if not str(payload.get("next_action") or "").strip():
        issues.append("next_action_missing")
    blocking_reason = str(payload.get("blocking_reason") or "")
    if passed and blocking_reason:
        issues.append("pass_probe_has_blocking_reason")
    if not passed and not blocking_reason:
        issues.append("blocked_probe_missing_blocking_reason")
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    total_checks = progress.get("totalChecks")
    passed_checks = progress.get("passedChecks")
    blocked_checks = progress.get("blockedChecks") if isinstance(progress.get("blockedChecks"), list) else None
    if not isinstance(total_checks, int) or total_checks < len(REQUIRED_PASS_FLAGS):
        issues.append("progress_total_checks_invalid")
    if not isinstance(passed_checks, int) or passed_checks < 0:
        issues.append("progress_passed_checks_invalid")
    if blocked_checks is None:
        issues.append("progress_blocked_checks_missing")
    elif passed and blocked_checks:
        issues.append("pass_probe_has_progress_blocked_checks")

    if payload.get("deployedRouteClaimAllowed") is not passed:
        issues.append("deployed_route_claim_mismatch")
    if payload.get("goldEligible") is not passed:
        issues.append("gold_eligible_mismatch")
    if payload.get("local_fixture_artifacts") is not False:
        issues.append("local_fixture_artifacts_not_false")
    if payload.get("live_provider_artifacts_verified") is not True:
        issues.append("live_provider_artifacts_not_verified")
    if payload.get("live_provider_delivery_verified") is not True:
        issues.append("live_provider_delivery_not_verified")
    if payload.get("rawCredentialExposed") is not False:
        issues.append("raw_credential_exposed")
    if payload.get("rawSessionTokenExposed") is not False:
        issues.append("raw_session_token_exposed")

    owner_auth = payload.get("ownerAuth") if isinstance(payload.get("ownerAuth"), dict) else {}
    if owner_auth.get("tokenValueStoredInReceipt") is not False:
        issues.append("owner_auth_token_value_stored")
    mode = owner_auth.get("mode")
    if mode not in {"cookie", "bearer"}:
        issues.append(f"unexpected_owner_auth_mode:{mode}")
    if mode == "cookie" and not str(owner_auth.get("cookieName") or "").strip():
        issues.append("cookie_auth_missing_cookie_name")
    if passed and not str(owner_auth.get("tokenSha256") or "").strip():
        issues.append("pass_probe_missing_token_sha256")

    env_file = payload.get("envFile") if isinstance(payload.get("envFile"), dict) else {}
    if env_file.get("valuesStoredInReceipt") is not False:
        issues.append("env_file_values_stored")

    for flag in PRIVATE_ROUTE_FLAGS:
        if payload.get(flag) is not True:
            issues.append(f"private_route_flag_not_true:{flag}")

    blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    if passed:
        for flag in REQUIRED_PASS_FLAGS:
            if payload.get(flag) is not True:
                issues.append(f"pass_flag_not_true:{flag}")
        if blockers != []:
            issues.append("pass_probe_has_blockers")
        if payload.get("owner_playback_e2e_verified") is not True:
            issues.append("pass_probe_owner_playback_not_verified")
    else:
        if "owner_playback_e2e_verified" not in blockers:
            issues.append("blocked_probe_missing_owner_playback_blocker")
        if "missing_deployed_identity_token" in blockers and owner_auth.get("tokenSha256"):
            issues.append("missing_token_blocker_with_token_hash")

    url_hashes = payload.get("url_hashes") if isinstance(payload.get("url_hashes"), dict) else {}
    for key in ("owner", "read", "book", "listen", "watch", "cover", "audiobookshelf_redirect", "audiobookshelf_dossier_redirect"):
        value = str(url_hashes.get(key) or "")
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
            issues.append(f"url_hash_invalid:{key}")
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    project_id = str(payload.get("projectId") or payload.get("project_id") or "").strip()
    if base_url and project_id:
        expected_routes = {
            "owner": origin_owner_url(base_url, project_id),
            "read": origin_owner_url(base_url, project_id, "read"),
            "book": origin_owner_url(base_url, project_id, "book"),
            "listen": origin_owner_url(base_url, project_id, "listen"),
            "watch": origin_owner_url(base_url, project_id, "video"),
            "cover": origin_owner_url(base_url, project_id, "cover"),
        }
        for key, expected_url in expected_routes.items():
            if url_hashes.get(key) != sha256_text(expected_url):
                issues.append(f"url_hash_mismatch:{key}")
        raw_route_fields = {
            "owner": "owner_detail_page",
            "read": "read_url",
            "book": "book_url",
            "listen": "listen_url",
            "watch": "watch_url",
            "cover": "selected_face_cover_url",
        }
        for key, field in raw_route_fields.items():
            raw_value = str(payload.get(field) or "").strip()
            if raw_value and raw_value != expected_routes[key]:
                issues.append(f"raw_route_mismatch:{field}")
            if raw_value and sha256_text(raw_value) != url_hashes.get(key):
                issues.append(f"raw_route_hash_mismatch:{field}")
    else:
        issues.append("base_url_or_project_id_missing")
    raw_share_fields = {
        "audiobookshelf_redirect": "audiobookshelf_redirect",
        "audiobookshelf_dossier_redirect": "audiobookshelf_dossier_redirect",
    }
    for key, field in raw_share_fields.items():
        raw_value = str(payload.get(field) or "").strip()
        if raw_value and sha256_text(raw_value) != url_hashes.get(key):
            issues.append(f"raw_share_hash_mismatch:{field}")

    return not issues, issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the deployed Origin Dossier browser probe receipt.")
    parser.add_argument(
        "--probe",
        type=Path,
        default=deployed_browser_probe_from_env(),
    )
    parser.add_argument("--require-pass", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ok, issues = verify(args.probe, require_pass=args.require_pass)
    if not ok:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    print("origin dossier deployed browser probe verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
