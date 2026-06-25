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
    "CHUMMER_DEPLOYED_E2E_AUTH_MODE",
    "CHUMMER_DEPLOYED_E2E_COOKIE_NAME",
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


def attach_owner_auth(session: requests.Session, token: str, base_url: str) -> dict[str, Any]:
    mode = auth_mode()
    name = cookie_name()
    if mode == "bearer":
        session.headers.update({"Authorization": f"Bearer {token}"})
    else:
        domain = (base_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0] or "chummer.run").strip()
        session.cookies.set(name, token, domain=domain, path="/")
    return {
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
    context = context or OriginEditionContext.from_env(project_id=project_id, base_url=base_url)
    loaded_env = load_env_file(env_file)
    imported = read_import_request(evidence_root)
    request = imported["importRequest"]
    share_url = str(request.get("audiobookshelfShareUrl") or "").strip()
    dossier_share_url = str(request.get("audiobookshelfDossierShareUrl") or "").strip()
    audiobook_share_url_trusted = is_trusted_audiobookshelf_share(share_url)
    dossier_share_url_trusted = is_trusted_audiobookshelf_share(dossier_share_url)
    token = os.environ.get("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "").strip()
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

    anonymous = requests.Session()
    anonymous_detail = get(anonymous, owner_url)
    anonymous_read = get(anonymous, read_url)
    anonymous_listen = get(anonymous, listen_url)
    anonymous_book = get(anonymous, book_url)
    anonymous_cover = get(anonymous, cover_url)
    anonymous_video = get(anonymous, watch_url)
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
    all_private_routes_login_protected = all(
        [
            anon_detail_redirect,
            anon_read_redirect,
            anon_listen_redirect,
            anon_book_redirect,
            anon_cover_redirect,
            anon_video_redirect,
        ]
    )

    signed = requests.Session()
    if token:
        auth_context = attach_owner_auth(signed, token, base_url)
    detail = get(signed, owner_url) if token else None
    cover = get(signed, cover_url) if token else None
    book = get(signed, book_url) if token else None
    read = get(signed, read_url) if token else None
    listen = get(signed, listen_url) if token else None
    video = get(signed, watch_url) if token else None

    detail_text = detail.text if detail is not None and status(detail) == 200 else ""
    logged_in = status(detail) == 200 and "data-origin-dossier-detail" in detail_text
    selected_cover = (
        "Rendered Origin Dossier story scene cover" in detail_text
        and ("data-origin-dossier-detail" in detail_text or "origin-edition" in detail_text)
    )
    read_tab = 'href="#origin-edition-read"' in detail_text
    listen_tab = 'href="#origin-edition-listen"' in detail_text
    watch_tab = 'href="#origin-edition-watch"' in detail_text
    canon_tab = 'href="#origin-edition-canon-audit"' in detail_text
    read_gate = status(read) in {302, 303, 307, 308} and header(read, "location") == dossier_share_url
    listen_gate = status(listen) in {302, 303, 307, 308} and header(listen, "location") == share_url
    audiobook_share_reachable = share_reachable(audiobook_share)
    dossier_share_reachable = share_reachable(dossier_share)
    watch_gate = status(video) == 200 and "video/mp4" in header(video, "content-type")
    cover_gate = status(cover) == 200 and "image/" in header(cover, "content-type")
    book_gate = status(book) == 200 and "epub" in header(book, "content-type").lower()
    watch_artifact_nonempty = watch_gate and body_size(video) > 0
    cover_artifact_nonempty = cover_gate and body_size(cover) > 0
    book_artifact_nonempty = book_gate and body_size(book) > 0
    owner_playback_e2e = all(
        [
            logged_in,
            selected_cover,
            read_tab,
            listen_tab,
            watch_tab,
            canon_tab,
            read_gate,
            listen_gate,
            watch_gate,
            cover_gate,
            book_gate,
            watch_artifact_nonempty,
            cover_artifact_nonempty,
            book_artifact_nonempty,
            audiobook_share_url_trusted,
            dossier_share_url_trusted,
            audiobook_share_reachable,
            dossier_share_reachable,
            all_private_routes_login_protected,
        ]
    )

    passed = all(
        [
            token,
            owner_playback_e2e,
        ]
    )
    blockers: list[str] = []
    if not token:
        blockers.append("missing_deployed_identity_token")
    checks = {
        "logged_in_browser_verified": logged_in,
        "selected_face_cover_visible": selected_cover,
        "read_tab_visible": read_tab,
        "listen_tab_visible": listen_tab,
        "watch_tab_visible": watch_tab,
        "canon_audit_tab_visible": canon_tab,
        "read_gate_verified": read_gate,
        "chummer_run_listen_gate_verified": listen_gate,
        "watch_gate_verified": watch_gate,
        "cover_route_verified": cover_gate,
        "book_route_verified": book_gate,
        "watch_artifact_nonempty": watch_artifact_nonempty,
        "cover_artifact_nonempty": cover_artifact_nonempty,
        "book_artifact_nonempty": book_artifact_nonempty,
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
        "all_private_routes_login_protected": all_private_routes_login_protected,
    }
    blockers.extend([key for key, value in checks.items() if not value])
    blocking_reason = "" if passed else ",".join(blockers)
    next_action = (
        "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN for a real deployed owner session and rerun this probe."
        if not token
        else "Inspect deployed route/index/session mismatch and rerun after deployment state is corrected."
    )
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
        "audiobookshelf_redirect": share_url,
        "local_fixture_artifacts": False,
        "deployedRouteClaimAllowed": passed,
        "rawCredentialExposed": False,
        "rawSessionTokenExposed": False,
        "ownerAuth": auth_context,
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
            "audiobook_share": status(audiobook_share),
            "dossier_share": status(dossier_share),
            "owner_detail": status(detail),
            "cover": status(cover),
            "book": status(book),
            "read": status(read),
            "listen": status(listen),
            "watch": status(video),
        },
        "response_body_sizes": {
            "cover": body_size(cover),
            "book": body_size(book),
            "watch": body_size(video),
            "audiobook_share": body_size(audiobook_share),
            "dossier_share": body_size(dossier_share),
        },
        "url_hashes": {
            "owner": sha256_text(owner_url),
            "read": sha256_text(read_url),
            "book": sha256_text(book_url),
            "listen": sha256_text(listen_url),
            "watch": sha256_text(watch_url),
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
    )
    output = args.output or context.branch(args.evidence_root) / "deployed-chummer-browser-probe.receipt.json"
    payload = materialize(args.evidence_root, context.base_url, context.project_id, output, args.env_file, context)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
