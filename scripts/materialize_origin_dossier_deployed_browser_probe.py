#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_context import OriginEditionContext
from origin_edition_provider_config import is_trusted_audiobookshelf_share


DEFAULT_EVIDENCE_ROOT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold")
DEFAULT_COOKIE_NAME = "chummer_hub_access_token"
E2E_ENV_KEYS = {
    "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN",
    "CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN",
    "CHUMMER_DEPLOYED_E2E_AUTH_MODE",
    "CHUMMER_DEPLOYED_E2E_COOKIE_NAME",
    "CHUMMER_DEPLOYED_E2E_COOKIE_HEADER",
    "CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER",
}


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


def auth_mode() -> str:
    mode = os.environ.get("CHUMMER_DEPLOYED_E2E_AUTH_MODE", "cookie").strip().lower()
    return mode if mode in {"cookie", "bearer"} else "cookie"


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
        domain = (base_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0] or "chummer.run").strip()
        session.cookies.set(name, token, domain=domain, path="/")
    return True, {
        "mode": mode,
        "cookieName": name if mode == "cookie" else None,
        "tokenSha256": sha256_text(token),
        "tokenValueStoredInReceipt": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe deployed chummer.run Origin Dossier owner route proof.")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--base-url")
    parser.add_argument("--project-id")
    parser.add_argument("--family-name")
    parser.add_argument("--given-name")
    parser.add_argument("--runner-name")
    parser.add_argument("--namespace")
    parser.add_argument("--env-file", type=Path, help="Optional local env file containing CHUMMER_DEPLOYED_E2E_* values.")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_text(value: object) -> str:
    text = str(value or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def read_import_request(evidence_root: Path) -> dict[str, Any]:
    path = evidence_root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or not isinstance(parsed.get("importRequest"), dict):
        raise ValueError("live import request is missing importRequest")
    return parsed


def read_deployed_state_import(evidence_root: Path, context: OriginEditionContext) -> dict[str, Any]:
    path = context.branch(evidence_root) / "deployed-state-import.receipt.json"
    if not path.is_file():
        return {
            "present": False,
            "status": "",
            "restartRequiredForExistingContainer": None,
            "receiptSha256": "",
        }
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "present": True,
            "status": "unreadable",
            "restartRequiredForExistingContainer": None,
            "receiptSha256": sha256_text(path.as_posix()),
        }
    if not isinstance(parsed, dict):
        return {
            "present": True,
            "status": "invalid",
            "restartRequiredForExistingContainer": None,
            "receiptSha256": sha256_text(path.as_posix()),
        }
    return {
        "present": True,
        "status": str(parsed.get("status") or "").strip(),
        "restartRequiredForExistingContainer": parsed.get("restartRequiredForExistingContainer"),
        "receiptSha256": sha256_text(path.as_posix()),
        "publicationIndexSha256": str(parsed.get("publicationIndexSha256") or "").strip(),
        "copiedArtifactCount": len(parsed.get("copiedArtifacts", [])) if isinstance(parsed.get("copiedArtifacts"), list) else 0,
    }


def get(session: requests.Session, url: str) -> requests.Response | None:
    try:
        return session.get(url, allow_redirects=False, timeout=30)
    except requests.RequestException:
        return None


def status(response: requests.Response | None) -> int | None:
    return response.status_code if response is not None else None


def header(response: requests.Response | None, name: str) -> str:
    return response.headers.get(name, "") if response is not None else ""


def body_size(response: requests.Response | None) -> int:
    if response is None:
        return 0
    return len(response.content or b"")


def response_sha256(response: requests.Response | None) -> str:
    if response is None:
        return ""
    return hashlib.sha256(response.content or b"").hexdigest()


def share_reachable(response: requests.Response | None) -> bool:
    if status(response) != 200:
        return False
    content_type = header(response, "content-type").lower()
    return body_size(response) > 0 and any(token in content_type for token in ("text/html", "application/xhtml", "application/json"))


def materialize(
    evidence_root: Path,
    base_url: str,
    project_id: str,
    output: Path,
    env_file: Path | None = None,
    context: OriginEditionContext | None = None,
) -> dict[str, Any]:
    evidence_root = evidence_root.resolve()
    base_url = base_url.rstrip("/")
    context = context or OriginEditionContext.from_env(project_id=project_id, base_url=base_url, require_explicit=True)
    loaded_env = load_env_file(env_file)
    imported = read_import_request(evidence_root)
    request = imported["importRequest"]
    live_evidence = imported.get("evidence") if isinstance(imported.get("evidence"), dict) else {}
    deployed_state_import = read_deployed_state_import(evidence_root, context)
    expected_cover_sha = str(live_evidence.get("storySceneCoverSha256") or "").strip()
    expected_book_sha = str(live_evidence.get("ebookArtifactSha256") or live_evidence.get("bookArtifactSha256") or "").strip()
    expected_video_sha = str(live_evidence.get("dossierVideoSha256") or "").strip()
    share_url = str(request.get("audiobookshelfAudiobookShareUrl") or request.get("audiobookshelfShareUrl") or "").strip()
    dossier_share_url = str(request.get("audiobookshelfDossierShareUrl") or "").strip()
    audiobook_share_url_trusted = is_trusted_audiobookshelf_share(share_url)
    dossier_share_url_trusted = is_trusted_audiobookshelf_share(dossier_share_url)
    has_owner_auth = False
    auth_context: dict[str, Any] = {
        "mode": auth_mode(),
        "cookieName": cookie_name() if auth_mode() == "cookie" else None,
        "tokenSha256": "",
        "tokenValueStoredInReceipt": False,
    }

    owner_url = f"{base_url}/account/work/origin-dossiers/{project_id}"
    read_url = f"{owner_url}/read"
    listen_url = f"{owner_url}/listen"
    book_url = f"{owner_url}/book"
    cover_url = f"{owner_url}/cover"
    watch_url = f"{owner_url}/video"
    canon_audit_url = f"{owner_url}/canon-audit"

    anonymous = requests.Session()
    anonymous_detail = get(anonymous, owner_url)
    anonymous_read = get(anonymous, read_url)
    anonymous_listen = get(anonymous, listen_url)
    anonymous_book = get(anonymous, book_url)
    anonymous_cover = get(anonymous, cover_url)
    anonymous_video = get(anonymous, watch_url)
    anonymous_canon_audit = get(anonymous, canon_audit_url)
    share_session = requests.Session()
    audiobook_share = get(share_session, share_url) if share_url else None
    dossier_share = get(share_session, dossier_share_url) if dossier_share_url else None

    def login_redirect(response: requests.Response | None) -> bool:
        return status(response) in {302, 303, 307, 308} and "/login?next=" in header(response, "location")

    anon_detail_redirect = status(anonymous_detail) in {302, 303, 307, 308} and "/login?next=" in header(anonymous_detail, "location")
    anon_read_redirect = login_redirect(anonymous_read)
    anon_listen_redirect = login_redirect(anonymous_listen)
    anon_book_redirect = login_redirect(anonymous_book)
    anon_cover_redirect = login_redirect(anonymous_cover)
    anon_video_redirect = login_redirect(anonymous_video)
    anon_canon_audit_redirect = login_redirect(anonymous_canon_audit)
    all_private_routes_login_protected = all(
        [
            anon_detail_redirect,
            anon_read_redirect,
            anon_listen_redirect,
            anon_book_redirect,
            anon_cover_redirect,
            anon_video_redirect,
            anon_canon_audit_redirect,
        ]
    )

    signed = requests.Session()
    has_owner_auth, auth_context = attach_owner_auth(signed, base_url)
    detail = get(signed, owner_url) if has_owner_auth else None
    cover = get(signed, cover_url) if has_owner_auth else None
    book = get(signed, book_url) if has_owner_auth else None
    read = get(signed, read_url) if has_owner_auth else None
    listen = get(signed, listen_url) if has_owner_auth else None
    video = get(signed, watch_url) if has_owner_auth else None
    canon_audit = get(signed, canon_audit_url) if has_owner_auth else None

    detail_text = detail.text if detail is not None and status(detail) == 200 else ""
    logged_in = status(detail) == 200 and "data-origin-dossier-detail" in detail_text
    cover_route = f'{cover_url}"'
    cover_alt = f'Rendered Origin Dossier story scene cover for {context.runner_name}'
    selected_cover_marker = 'data-story-scene-cover-uses-selected-character-face="true"' in detail_text
    selected_cover_alt = cover_alt in detail_text
    selected_cover_route = cover_route in detail_text
    selected_cover = selected_cover_marker and selected_cover_alt and selected_cover_route
    read_link = 'href="#origin-edition-read"' in detail_text
    listen_link = 'href="#origin-edition-listen"' in detail_text
    watch_link = 'href="#origin-edition-watch"' in detail_text
    read_section = 'id="origin-edition-read"' in detail_text and 'data-origin-edition-tab="read"' in detail_text
    listen_section = 'id="origin-edition-listen"' in detail_text and 'data-origin-edition-tab="listen"' in detail_text
    watch_section = 'id="origin-edition-watch"' in detail_text and 'data-origin-edition-tab="watch"' in detail_text
    read_tab = read_link and read_section
    listen_tab = listen_link and listen_section
    watch_tab = watch_link and watch_section
    canon_tab = 'href="#origin-edition-canon-audit"' in detail_text
    canon_section = 'id="origin-edition-canon-audit"' in detail_text and 'data-origin-edition-tab="canon-audit"' in detail_text
    chummer_canon_owner = 'data-chummer-owns-canon="true"' in detail_text
    provider_created_facts_blocked = 'data-provider-created-facts-auto-canon="false"' in detail_text
    canon_privacy_receipts_present = 'data-canon-privacy-receipts-present="true"' in detail_text
    no_fallback_media_verified = 'data-no-fallback-media-verified="true"' in detail_text
    canon_audit_content_verified = all(
        [
            canon_tab,
            canon_section,
            chummer_canon_owner,
            provider_created_facts_blocked,
            canon_privacy_receipts_present,
            no_fallback_media_verified,
        ]
    )
    read_gate = status(read) in {302, 303, 307, 308} and header(read, "location") == dossier_share_url
    listen_gate = status(listen) in {302, 303, 307, 308} and header(listen, "location") == share_url
    audiobook_share_reachable = share_reachable(audiobook_share)
    dossier_share_reachable = share_reachable(dossier_share)
    watch_gate = status(video) == 200 and "video/mp4" in header(video, "content-type")
    cover_gate = status(cover) == 200 and "image/" in header(cover, "content-type")
    book_gate = status(book) == 200 and "epub" in header(book, "content-type").lower()
    canon_audit_route = status(canon_audit) == 200 and "application/json" in header(canon_audit, "content-type")
    watch_artifact_nonempty = watch_gate and body_size(video) > 0
    cover_artifact_nonempty = cover_gate and body_size(cover) > 0
    book_artifact_nonempty = book_gate and body_size(book) > 0
    cover_sha_matches_import = cover_artifact_nonempty and bool(expected_cover_sha) and response_sha256(cover) == expected_cover_sha
    book_sha_matches_import = book_artifact_nonempty and bool(expected_book_sha) and response_sha256(book) == expected_book_sha
    video_sha_matches_import = watch_artifact_nonempty and bool(expected_video_sha) and response_sha256(video) == expected_video_sha
    owner_playback_e2e = all(
        [
            logged_in,
            selected_cover,
            read_tab,
            listen_tab,
            watch_tab,
            canon_tab,
            canon_audit_content_verified,
            canon_audit_route,
            read_gate,
            listen_gate,
            watch_gate,
            cover_gate,
            book_gate,
            watch_artifact_nonempty,
            cover_artifact_nonempty,
            book_artifact_nonempty,
            cover_sha_matches_import,
            book_sha_matches_import,
            video_sha_matches_import,
            audiobook_share_url_trusted,
            dossier_share_url_trusted,
            audiobook_share_reachable,
            dossier_share_reachable,
            all_private_routes_login_protected,
        ]
    )

    passed = all(
        [
            has_owner_auth,
            owner_playback_e2e,
        ]
    )
    blockers: list[str] = []
    if not has_owner_auth:
        blockers.append("missing_deployed_owner_session")
    checks = {
        "logged_in_browser_verified": logged_in,
        "selected_face_cover_marker_visible": selected_cover_marker,
        "selected_face_cover_alt_visible": selected_cover_alt,
        "selected_face_cover_route_visible": selected_cover_route,
        "selected_face_cover_visible": selected_cover,
        "read_tab_visible": read_tab,
        "read_section_visible": read_section,
        "listen_tab_visible": listen_tab,
        "listen_section_visible": listen_section,
        "watch_tab_visible": watch_tab,
        "watch_section_visible": watch_section,
        "canon_audit_tab_visible": canon_tab,
        "canon_audit_section_visible": canon_section,
        "chummer_canon_owner_visible": chummer_canon_owner,
        "provider_created_facts_blocked_visible": provider_created_facts_blocked,
        "canon_privacy_receipts_present": canon_privacy_receipts_present,
        "no_fallback_media_verified": no_fallback_media_verified,
        "canon_audit_content_verified": canon_audit_content_verified,
        "canon_audit_route_verified": canon_audit_route,
        "read_gate_verified": read_gate,
        "chummer_run_listen_gate_verified": listen_gate,
        "watch_gate_verified": watch_gate,
        "cover_route_verified": cover_gate,
        "book_route_verified": book_gate,
        "watch_artifact_nonempty": watch_artifact_nonempty,
        "cover_artifact_nonempty": cover_artifact_nonempty,
        "book_artifact_nonempty": book_artifact_nonempty,
        "cover_sha_matches_import": cover_sha_matches_import,
        "book_sha_matches_import": book_sha_matches_import,
        "video_sha_matches_import": video_sha_matches_import,
        "audiobook_share_url_trusted": audiobook_share_url_trusted,
        "dossier_share_url_trusted": dossier_share_url_trusted,
        "audiobook_share_reachable": audiobook_share_reachable,
        "dossier_share_reachable": dossier_share_reachable,
        "owner_playback_e2e_verified": owner_playback_e2e,
        "unauthenticated_detail_redirect_verified": anon_detail_redirect,
        "unauthenticated_read_redirect_verified": anon_read_redirect,
        "unauthenticated_listen_redirect_verified": anon_listen_redirect,
        "unauthenticated_book_redirect_verified": anon_book_redirect,
        "unauthenticated_cover_redirect_verified": anon_cover_redirect,
        "unauthenticated_video_redirect_verified": anon_video_redirect,
        "unauthenticated_canon_audit_redirect_verified": anon_canon_audit_redirect,
        "all_private_routes_login_protected": all_private_routes_login_protected,
    }
    blockers.extend([key for key, value in checks.items() if not value])
    blocking_reason = "" if passed else ",".join(blockers)
    if not has_owner_auth:
        next_action = "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN, CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN, CHUMMER_DEPLOYED_E2E_COOKIE_HEADER, or CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER for a real deployed owner session and rerun this probe."
    elif (
        status(detail) == 404
        and deployed_state_import.get("status") == "verified"
        and deployed_state_import.get("restartRequiredForExistingContainer") is True
    ):
        next_action = "Restart/recreate chummer-portal only after explicit deploy approval so CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=/app/state/origin-dossier-publications.json is active, then rerun this probe."
    else:
        next_action = "Inspect deployed route/index/session mismatch and rerun after deployment state is corrected."
    progress = {
        "passedChecks": sum(1 for value in checks.values() if value),
        "totalChecks": len(checks),
        "blockedChecks": [key for key, value in checks.items() if not value],
    }

    payload: dict[str, Any] = {
        "contractName": "chummer.origin_edition.deployed_browser_probe.v1",
        "generated_at_utc": now_iso(),
        "updated_at": now_iso(),
        "status": "pass" if passed else "blocked",
        "goldEligible": passed,
        "namespace": context.resolved_namespace,
        "projectId": project_id,
        "project_id": project_id,
        "base_url": base_url,
        "owner_account_page": f"{base_url}/account/work#origin-dossier-library",
        "owner_detail_page": owner_url,
        "selected_face_cover_url": cover_url,
        "read_url": read_url,
        "book_url": book_url,
        "listen_url": listen_url,
        "watch_url": watch_url,
        "canon_audit_url": canon_audit_url,
        "audiobookshelf_redirect": share_url,
        "local_fixture_artifacts": False,
        "deployedRouteClaimAllowed": passed,
        "rawCredentialExposed": False,
        "rawSessionTokenExposed": False,
        "ownerAuth": auth_context,
        "deployedStateImport": deployed_state_import,
        "envFile": {
            "provided": env_file is not None,
            "pathSha256": sha256_text(env_file.as_posix()) if env_file is not None else "",
            "loadedKeys": sorted(loaded_env.keys()),
            "valuesStoredInReceipt": False,
        },
        "live_provider_artifacts_verified": True,
        "live_provider_delivery_verified": True,
        **checks,
        "http_statuses": {
            "anonymous_detail": status(anonymous_detail),
            "anonymous_read": status(anonymous_read),
            "anonymous_listen": status(anonymous_listen),
            "anonymous_book": status(anonymous_book),
            "anonymous_cover": status(anonymous_cover),
            "anonymous_video": status(anonymous_video),
            "anonymous_canon_audit": status(anonymous_canon_audit),
            "audiobook_share": status(audiobook_share),
            "dossier_share": status(dossier_share),
            "owner_detail": status(detail),
            "cover": status(cover),
            "book": status(book),
            "read": status(read),
            "listen": status(listen),
            "watch": status(video),
            "canon_audit": status(canon_audit),
        },
        "response_body_sizes": {
            "cover": body_size(cover),
            "book": body_size(book),
            "watch": body_size(video),
            "canon_audit": body_size(canon_audit),
            "audiobook_share": body_size(audiobook_share),
            "dossier_share": body_size(dossier_share),
        },
        "response_sha256": {
            "cover": response_sha256(cover),
            "book": response_sha256(book),
            "watch": response_sha256(video),
            "canon_audit": response_sha256(canon_audit),
        },
        "redirect_location_sha256": {
            "read": sha256_text(header(read, "location")),
            "listen": sha256_text(header(listen, "location")),
        },
        "expected_redirect_location_sha256": {
            "read": sha256_text(dossier_share_url),
            "listen": sha256_text(share_url),
        },
        "expected_import_sha256": {
            "cover": expected_cover_sha,
            "book": expected_book_sha,
            "watch": expected_video_sha,
        },
        "url_hashes": {
            "owner": sha256_text(owner_url),
            "read": sha256_text(read_url),
            "book": sha256_text(book_url),
            "listen": sha256_text(listen_url),
            "watch": sha256_text(watch_url),
            "canon_audit": sha256_text(canon_audit_url),
            "cover": sha256_text(cover_url),
            "audiobookshelf_redirect": sha256_text(share_url),
            "audiobookshelf_dossier_redirect": sha256_text(dossier_share_url),
        },
        "blockers": blockers,
        "blocking_reason": blocking_reason,
        "next_action": next_action,
        "nextOperatorAction": next_action,
        "progress": progress,
        "loginNextHash": sha256_text(f"/login?next={quote(f'/account/work/origin-dossiers/{project_id}', safe='')}"),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    args = parse_args()
    context = OriginEditionContext.from_env(
        project_id=args.project_id,
        family_name=args.family_name,
        given_name=args.given_name,
        runner_name=args.runner_name,
        namespace=args.namespace,
        base_url=args.base_url,
        require_explicit=True,
    )
    output = args.output or context.branch(args.evidence_root) / "deployed-chummer-browser-probe.receipt.json"
    payload = materialize(args.evidence_root, context.base_url, context.project_id, output, args.env_file, context)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
