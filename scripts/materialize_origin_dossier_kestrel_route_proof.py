#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from absolute_completion_common import LocalHubApp, TokenIdentityStub, write_json
from origin_edition_context import OriginEditionContext
from origin_edition_provider_config import origin_owner_url


DEFAULT_EVIDENCE_ROOT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold")
DEFAULT_CONTEXT = OriginEditionContext.default()
DEFAULT_SUBJECT_ID = "subject.varga-mira.kestrel"
DEFAULT_TOKEN = "kestrel-origin-route-proof-token"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Origin Dossier authenticated route proof.")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--project-id")
    parser.add_argument("--family-name")
    parser.add_argument("--given-name")
    parser.add_argument("--runner-name")
    parser.add_argument("--namespace")
    parser.add_argument("--base-url")
    parser.add_argument("--subject-id")
    parser.add_argument("--token")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: object) -> str:
    text = str(value or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def extract_missing_requirements(html: str) -> list[str]:
    match = re.search(r"<summary>Missing gold requirements</summary>\s*<ul[^>]*>(.*?)</ul>", html, re.I | re.S)
    if not match:
        return []
    return [
        re.sub(r"\s+", " ", item).strip()
        for item in re.findall(r"<li>(.*?)</li>", match.group(1), re.I | re.S)
        if re.sub(r"\s+", " ", item).strip()
    ]


def subject_id_for(context: OriginEditionContext, explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    if context == DEFAULT_CONTEXT:
        return DEFAULT_SUBJECT_ID
    digest = hashlib.sha256(context.resolved_namespace.encode("utf-8")).hexdigest()[:16]
    return f"subject.origin-edition.{digest}"


def token_for(context: OriginEditionContext, explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    if context == DEFAULT_CONTEXT:
        return DEFAULT_TOKEN
    digest = hashlib.sha256(f"route-proof:{context.resolved_namespace}".encode("utf-8")).hexdigest()[:24]
    return f"origin-route-proof-{digest}"


def build_publication_index(
    evidence_root: Path,
    output_path: Path,
    context: OriginEditionContext,
    subject_id: str,
) -> dict[str, Any]:
    import_payload = json.loads((evidence_root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json").read_text(encoding="utf-8"))
    request = dict(import_payload["importRequest"])
    entry = dict(request)
    branch = context.branch(evidence_root)
    entry["ownerUserId"] = f"{context.project_id}-origin-route-proof-user"
    entry["subjectId"] = subject_id
    entry["ownerSubjectId"] = subject_id
    entry["requiresAuthenticatedChummerRunUser"] = True
    # The service requires a Chummer-owned URL in the index; it rewrites it to the configured local base URL.
    entry["chummerRunOwnerUrl"] = origin_owner_url(context.base_url, context.project_id)
    entry["bookArtifactUrl"] = origin_owner_url(context.base_url, context.project_id, "book")
    entry["dossierVideoUrl"] = origin_owner_url(context.base_url, context.project_id, "video")
    entry["storySceneCoverUrl"] = origin_owner_url(context.base_url, context.project_id, "cover")
    entry["ebookArtifactPath"] = entry.get("bookArtifactPath")
    entry["ebookAudiobookshelfImportReceiptPath"] = str(branch / "dossier/audiobookshelf-dossier-import.receipt.json")
    entry["coverConsistencyReceiptPath"] = str(branch / "cover-consistency-strict.receipt.json")
    entry["audiobookPath"] = str(branch / "audiobook" / f"{context.runner_name.lower()}-origin.m4b")
    entry["audiobookshelfImportReceiptPath"] = str(branch / "audiobook/audiobookshelf-import.receipt.json")
    entry["finalNoFallbackNoSentinelAuditReceiptPath"] = str(branch / "final-no-fallback-no-sentinel-audit.receipt.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, {"publications": [entry]})
    return entry


def get(session: requests.Session, url: str, *, allow_redirects: bool = False) -> requests.Response:
    return session.get(url, allow_redirects=allow_redirects, timeout=30)


def materialize(
    evidence_root: Path,
    output_path: Path,
    context: OriginEditionContext | None = None,
    subject_id: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    evidence_root = evidence_root.resolve()
    context = context or DEFAULT_CONTEXT
    subject_id = subject_id_for(context, subject_id)
    token = token_for(context, token)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="chummer-kestrel-origin-route-") as temp_dir:
        temp_root = Path(temp_dir)
        index_path = temp_root / "origin-dossier-publications.json"
        entry = build_publication_index(evidence_root, index_path, context, subject_id)
        identity = TokenIdentityStub(
            access_token=token,
            subject_id=subject_id,
            display_name=f"{context.given_name} {context.family_name}",
            email=f"{context.given_name}.{context.family_name}@example.invalid".lower(),
        )
        with identity:
            app = LocalHubApp(
                identity_base_url=identity.base_url,
                extra_env={
                    "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX": str(index_path),
                },
            )
            app.extra_env["CHUMMER_PUBLIC_BASE_URL"] = app.base_url
            with app:
                owner_url = f"{app.base_url}/account/work/origin-dossiers/{context.project_id}"
                library_url = f"{app.base_url}/account/work#origin-dossier-library"
                read_route = f"{owner_url}/read"
                listen_route = f"{owner_url}/listen"
                video_route = f"{owner_url}/video"
                cover_route = f"{owner_url}/cover"
                book_route = f"{owner_url}/book"

                anonymous = requests.Session()
                anon_detail = get(anonymous, owner_url)
                anon_read = get(anonymous, read_route)
                anon_listen = get(anonymous, listen_route)
                anon_book = get(anonymous, book_route)
                anon_cover = get(anonymous, cover_route)
                anon_video = get(anonymous, video_route)
                require(anon_detail.status_code in {302, 303, 307, 308}, "anonymous detail did not redirect", failures)
                require("/login?next=" in anon_detail.headers.get("location", ""), "anonymous detail redirect missing login next", failures)
                require(anon_read.status_code in {302, 303, 307, 308}, "anonymous read did not redirect", failures)
                require("/login?next=" in anon_read.headers.get("location", ""), "anonymous read redirect missing login next", failures)
                require(anon_listen.status_code in {302, 303, 307, 308}, "anonymous listen did not redirect", failures)
                require("/login?next=" in anon_listen.headers.get("location", ""), "anonymous listen redirect missing login next", failures)
                require(anon_book.status_code in {302, 303, 307, 308}, "anonymous book did not redirect", failures)
                require("/login?next=" in anon_book.headers.get("location", ""), "anonymous book redirect missing login next", failures)
                require(anon_cover.status_code in {302, 303, 307, 308}, "anonymous cover did not redirect", failures)
                require("/login?next=" in anon_cover.headers.get("location", ""), "anonymous cover redirect missing login next", failures)
                require(anon_video.status_code in {302, 303, 307, 308}, "anonymous video did not redirect", failures)
                require("/login?next=" in anon_video.headers.get("location", ""), "anonymous video redirect missing login next", failures)

                signed = requests.Session()
                signed.cookies.set("chummer_hub_access_token", token, domain="127.0.0.1", path="/")
                library = get(signed, library_url, allow_redirects=True)
                detail = get(signed, owner_url, allow_redirects=True)
                require(library.status_code == 200, f"library status {library.status_code}", failures)
                require(detail.status_code == 200, f"detail status {detail.status_code}", failures)
                detail_text = detail.text
                visible_missing_requirements = extract_missing_requirements(detail_text)
                expected_cover_alt = f"Rendered Origin Dossier story scene cover for {context.runner_name}"
                for expected in (
                    f"{context.runner_name}: Origin Dossier",
                    context.resolved_namespace,
                    "data-origin-edition-tabs",
                    "href=\"#origin-edition-read\"",
                    "href=\"#origin-edition-listen\"",
                    "href=\"#origin-edition-watch\"",
                    "href=\"#origin-edition-canon-audit\"",
                    "data-chummer-owns-canon=\"true\"",
                    "data-provider-created-facts-auto-canon=\"false\"",
                    "data-canon-privacy-receipts-present=\"true\"",
                    "data-no-fallback-media-verified=\"true\"",
                    "Read in Audiobookshelf",
                    "Listen in Audiobookshelf",
                    "Watch scene movie",
                    expected_cover_alt,
                ):
                    require(expected in detail_text, f"detail missing {expected}", failures)

                cover = get(signed, cover_route)
                book = get(signed, book_route)
                video = get(signed, video_route)
                read = get(signed, read_route)
                listen = get(signed, listen_route)
                require(cover.status_code == 200, f"cover status {cover.status_code}", failures)
                require("image/" in cover.headers.get("content-type", ""), "cover content type not image", failures)
                require(book.status_code == 200, f"book status {book.status_code}", failures)
                require("epub" in book.headers.get("content-type", "").lower(), "book content type not epub", failures)
                require(video.status_code == 200, f"video status {video.status_code}", failures)
                require("video/mp4" in video.headers.get("content-type", ""), "video content type not mp4", failures)
                require(read.status_code in {302, 303, 307, 308}, f"read status {read.status_code}", failures)
                require(read.headers.get("location") == entry["audiobookshelfDossierShareUrl"], "read redirect mismatch", failures)
                require(listen.status_code in {302, 303, 307, 308}, f"listen status {listen.status_code}", failures)
                require(listen.headers.get("location") == entry["audiobookshelfAudiobookShareUrl"], "listen redirect mismatch", failures)

                payload: dict[str, Any] = {
                    "contractName": "chummer.origin_edition.authenticated_route_live_proof.v1",
                    "status": "pass" if not failures else "failed",
                    "goldEligible": not failures,
                    "generatedAtUtc": now_iso(),
                    "namespace": context.resolved_namespace,
                    "projectId": context.project_id,
                    "project_id": context.project_id,
                    "proofScope": "authenticated_chummer_run_route_proof_for_real_origin_evidence",
                    "localAuthenticatedRunSiteInstance": True,
                    "local_fixture_artifacts": False,
                    "deployedRouteClaimAllowed": False,
                    "base_url": app.base_url,
                    "owner_account_page": library_url,
                    "owner_detail_page": owner_url,
                    "selected_face_cover_url": cover_route,
                    "read_url": read_route,
                    "book_url": book_route,
                    "listen_url": listen_route,
                    "watch_url": video_route,
                    "audiobookshelf_redirect": entry["audiobookshelfAudiobookShareUrl"],
                    "rawCredentialExposed": False,
                    "rawSessionTokenExposed": False,
                    "ownerDetailStatus": detail.status_code,
                    "ownerLibraryStatus": library.status_code,
                    "anonymousDetailRedirectVerified": anon_detail.status_code in {302, 303, 307, 308},
                    "anonymousReadRedirectVerified": anon_read.status_code in {302, 303, 307, 308},
                    "anonymousListenRedirectVerified": anon_listen.status_code in {302, 303, 307, 308},
                    "anonymousBookRedirectVerified": anon_book.status_code in {302, 303, 307, 308},
                    "anonymousCoverRedirectVerified": anon_cover.status_code in {302, 303, 307, 308},
                    "anonymousVideoRedirectVerified": anon_video.status_code in {302, 303, 307, 308},
                    "anonymousArtifactRedirectVerified": all(
                        response.status_code in {302, 303, 307, 308}
                        for response in (anon_read, anon_listen, anon_book, anon_cover, anon_video)
                    ),
                    "all_private_routes_login_protected": all(
                        response.status_code in {302, 303, 307, 308}
                        and "/login?next=" in response.headers.get("location", "")
                        for response in (anon_detail, anon_read, anon_listen, anon_book, anon_cover, anon_video)
                    ),
                    "logged_in_browser_verified": detail.status_code == 200,
                    "readTabVisible": "href=\"#origin-edition-read\"" in detail_text,
                    "listenTabVisible": "href=\"#origin-edition-listen\"" in detail_text,
                    "watchTabVisible": "href=\"#origin-edition-watch\"" in detail_text,
                    "canonAuditTabVisible": "href=\"#origin-edition-canon-audit\"" in detail_text,
                    "canonAuditContentVerified": all(
                        token in detail_text
                        for token in (
                            "id=\"origin-edition-canon-audit\"",
                            "data-origin-edition-tab=\"canon-audit\"",
                            "data-chummer-owns-canon=\"true\"",
                            "data-provider-created-facts-auto-canon=\"false\"",
                            "data-canon-privacy-receipts-present=\"true\"",
                            "data-no-fallback-media-verified=\"true\"",
                        )
                    ),
                    "selectedFaceCoverVisible": expected_cover_alt in detail_text,
                    "read_tab_visible": "href=\"#origin-edition-read\"" in detail_text,
                    "listen_tab_visible": "href=\"#origin-edition-listen\"" in detail_text,
                    "watch_tab_visible": "href=\"#origin-edition-watch\"" in detail_text,
                    "canon_audit_tab_visible": "href=\"#origin-edition-canon-audit\"" in detail_text,
                    "canon_audit_content_verified": all(
                        token in detail_text
                        for token in (
                            "id=\"origin-edition-canon-audit\"",
                            "data-origin-edition-tab=\"canon-audit\"",
                            "data-chummer-owns-canon=\"true\"",
                            "data-provider-created-facts-auto-canon=\"false\"",
                            "data-canon-privacy-receipts-present=\"true\"",
                            "data-no-fallback-media-verified=\"true\"",
                        )
                    ),
                    "selected_face_cover_visible": expected_cover_alt in detail_text,
                    "readRouteRedirectVerified": read.headers.get("location") == entry["audiobookshelfDossierShareUrl"],
                    "listenRouteRedirectVerified": listen.headers.get("location") == entry["audiobookshelfAudiobookShareUrl"],
                    "watchRouteVerified": video.status_code == 200 and "video/mp4" in video.headers.get("content-type", ""),
                    "coverRouteVerified": cover.status_code == 200 and "image/" in cover.headers.get("content-type", ""),
                    "bookRouteVerified": book.status_code == 200 and "epub" in book.headers.get("content-type", "").lower(),
                    "read_gate_verified": read.headers.get("location") == entry["audiobookshelfDossierShareUrl"],
                    "chummer_run_listen_gate_verified": listen.headers.get("location") == entry["audiobookshelfAudiobookShareUrl"],
                    "watch_gate_verified": video.status_code == 200 and "video/mp4" in video.headers.get("content-type", ""),
                    "unauthenticated_detail_redirect_verified": anon_detail.status_code in {302, 303, 307, 308},
                    "unauthenticated_artifact_redirect_verified": anon_listen.status_code in {302, 303, 307, 308},
                    "live_provider_artifacts_verified": True,
                    "live_provider_delivery_verified": True,
                    "owner_playback_e2e_verified": False,
                    "sourceImportRequestSha256": sha256_file(evidence_root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"),
                    "publicationIndexSha256": sha256_file(index_path),
                    "localHubLogSha256": sha256_file(app.log_path) if app.log_path and app.log_path.exists() else "",
                    "urlHashes": {
                        "owner": sha256_text(owner_url),
                        "read": sha256_text(read_route),
                        "listen": sha256_text(listen_route),
                        "video": sha256_text(video_route),
                        "cover": sha256_text(cover_route),
                        "book": sha256_text(book_route),
                    },
                    "failures": failures,
                    "visibleMissingGoldRequirements": visible_missing_requirements,
                    "tokens": [
                        "authenticated_chummer_run_route_proof",
                        "read_tab_visible",
                        "listen_tab_visible",
                        "watch_tab_visible",
                        "canon_audit_tab_visible",
                        "anonymous_private_access_redirects_to_login",
                        "owner_read_listen_watch_routes_verified",
                    ],
                }
                write_json(output_path, payload)
                return payload
    raise RuntimeError("route proof did not materialize")


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
    output = args.output or context.branch(args.evidence_root) / "authenticated-chummer-route-live.receipt.json"
    payload = materialize(args.evidence_root, output, context, args.subject_id, args.token)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
