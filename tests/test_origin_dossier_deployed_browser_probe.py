from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_dossier_deployed_browser_probe.py"
FAKE_COVER_BYTES = b"\xff\xd8cover-bytes"
FAKE_BOOK_BYTES = b"%PDF-1.7\nbook-bytes"
FAKE_EBOOK_BYTES = b"PK\x03\x04ebook-bytes"
FAKE_VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42movie-bytes"
FAKE_CANON_AUDIT_BYTES = b'{"status":"pass","tokens":["canon_audit_passed"]}'


def load_module():
    seed_origin_context_env()
    spec = importlib.util.spec_from_file_location("origin_dossier_deployed_browser_probe", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_origin_context_env() -> None:
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_PROJECT_ID", "varga-mira-kestrel")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_FAMILY_NAME", "Varga")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_GIVEN_NAME", "Mira")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_RUNNER_NAME", "Kestrel")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_BASE_URL", "https://chummer.run")


def clear_origin_context_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "CHUMMER_ORIGIN_EDITION_PROJECT_ID",
        "CHUMMER_ORIGIN_EDITION_FAMILY_NAME",
        "CHUMMER_ORIGIN_EDITION_GIVEN_NAME",
        "CHUMMER_ORIGIN_EDITION_RUNNER_NAME",
        "CHUMMER_ORIGIN_EDITION_BASE_URL",
        "CHUMMER_ORIGIN_EDITION_NAMESPACE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_deployed_probe_without_explicit_context_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    clear_origin_context_env(monkeypatch)

    with pytest.raises(ValueError, match="explicit Origin Edition context required"):
        module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", tmp_path / "probe.json")


def write_import_request(
    root: Path,
    *,
    audiobook_share_url: str = "https://audiobookshelf.girschele.com/audiobookshelf/share/audio",
    dossier_share_url: str = "https://audiobookshelf.girschele.com/audiobookshelf/share/book",
    legacy_audiobook_share_url: str | None = None,
    book_sha: str | None = None,
    legacy_ebook_sha: str | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json").write_text(
        json.dumps(
            {
                "evidence": {
                    "storySceneCoverSha256": hashlib.sha256(FAKE_COVER_BYTES).hexdigest(),
                    "bookArtifactSha256": book_sha or hashlib.sha256(FAKE_BOOK_BYTES).hexdigest(),
                    "ebookArtifactSha256": legacy_ebook_sha or hashlib.sha256(FAKE_EBOOK_BYTES).hexdigest(),
                    "dossierVideoSha256": hashlib.sha256(FAKE_VIDEO_BYTES).hexdigest(),
                },
                "importRequest": {
                    "bookArtifactPath": "/evidence/origin/book.pdf",
                    "ebookArtifactPath": "/evidence/origin/ebook.epub",
                    "audiobookshelfShareUrl": legacy_audiobook_share_url if legacy_audiobook_share_url is not None else audiobook_share_url,
                    "audiobookshelfAudiobookShareUrl": audiobook_share_url,
                    "audiobookshelfDossierShareUrl": dossier_share_url,
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None, text: str = "", content: bytes | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")


class FakeSession:
    def __init__(self) -> None:
        self.cookies = self
        self.headers: dict[str, str] = {}
        self.has_cookie = False

    def set(self, *_args, **_kwargs) -> None:
        self.has_cookie = True

    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        if "audiobookshelf.girschele.com/audiobookshelf/share/" in url:
            return FakeResponse(200, {"content-type": "text/html; charset=utf-8"}, "<main>Audiobookshelf share</main>")
        if (
            not self.has_cookie
            and not self.headers.get("Authorization")
            and not self.headers.get("Cookie")
        ):
            return FakeResponse(302, {"location": "/login?next=%2Faccount%2Fwork"})
        if url.endswith("/cover"):
            return FakeResponse(200, {"content-type": "image/jpeg"}, content=FAKE_COVER_BYTES)
        if url.endswith("/book"):
            return FakeResponse(200, {"content-type": "application/pdf"}, content=FAKE_BOOK_BYTES)
        if url.endswith("/read"):
            return FakeResponse(302, {"location": "https://audiobookshelf.girschele.com/audiobookshelf/share/book"})
        if url.endswith("/listen"):
            return FakeResponse(302, {"location": "https://audiobookshelf.girschele.com/audiobookshelf/share/audio"})
        if url.endswith("/video"):
            return FakeResponse(200, {"content-type": "video/mp4"}, content=FAKE_VIDEO_BYTES)
        if url.endswith("/canon-audit"):
            return FakeResponse(200, {"content-type": "application/json; charset=utf-8"}, content=FAKE_CANON_AUDIT_BYTES)
        return FakeResponse(
            200,
            {"content-type": "text/html"},
            """
            <main data-origin-dossier-detail>
              <article data-story-scene-cover-uses-selected-character-face="true">
                <img src="https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/cover" alt="Fitted Origin Dossier cover art for Kestrel">
              </article>
              <a href="#origin-edition-read">Read</a>
              <a href="#origin-edition-portraits">Portraits</a>
              <a href="#origin-edition-listen">Listen</a>
              <a href="#origin-edition-watch">Watch</a>
              <a href="#origin-edition-canon-audit">Canon notes</a>
              <section id="origin-edition-read" data-origin-edition-tab="read">Read the ebook</section>
              <section id="origin-edition-portraits" data-origin-edition-tab="portraits" data-origin-portrait-choice-count="3">Portrait shortlist</section>
              <section id="origin-edition-listen" data-origin-edition-tab="listen" data-origin-audiobook-voice-count="3">Listen in Audiobookshelf</section>
              <section id="origin-edition-watch" data-origin-edition-tab="watch" data-origin-scene-highlight-count="4">Watch selected cinematic scene</section>
              <section id="origin-edition-canon-audit"
                       data-origin-edition-tab="canon-audit"
                       data-chummer-owns-canon="true"
                       data-provider-created-facts-auto-canon="false"
                       data-canon-privacy-receipts-present="true"
                       data-no-fallback-media-verified="true">
                Canon notes
              </section>
            </main>
            """,
        )


class LeakyAnonymousVideoSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        if not self.has_cookie and not self.headers.get("Authorization", "").startswith("Bearer ") and url.endswith("/video"):
            return FakeResponse(200, {"content-type": "video/mp4"})
        return super().get(url, allow_redirects=allow_redirects, timeout=timeout)


class LeakyAnonymousCanonAuditSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        if not self.has_cookie and not self.headers.get("Authorization", "").startswith("Bearer ") and url.endswith("/canon-audit"):
            return FakeResponse(200, {"content-type": "application/json; charset=utf-8"}, content=FAKE_CANON_AUDIT_BYTES)
        return super().get(url, allow_redirects=allow_redirects, timeout=timeout)


class BrokenOwnerVideoSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        if (self.has_cookie or self.headers.get("Authorization", "").startswith("Bearer ")) and url.endswith("/video"):
            return FakeResponse(500, {"content-type": "text/plain"})
        return super().get(url, allow_redirects=allow_redirects, timeout=timeout)


class EmptyOwnerVideoSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        if (self.has_cookie or self.headers.get("Authorization", "").startswith("Bearer ")) and url.endswith("/video"):
            return FakeResponse(200, {"content-type": "video/mp4"}, content=b"")
        return super().get(url, allow_redirects=allow_redirects, timeout=timeout)


class WrongHashOwnerVideoSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        if (self.has_cookie or self.headers.get("Authorization", "").startswith("Bearer ")) and url.endswith("/video"):
            return FakeResponse(200, {"content-type": "video/mp4"}, content=b"\x00\x00\x00\x18ftypmp42wrong-movie")
        return super().get(url, allow_redirects=allow_redirects, timeout=timeout)


class BrokenAudiobookshelfShareSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        if "audiobookshelf.girschele.com/audiobookshelf/share/audio" in url:
            return FakeResponse(503, {"content-type": "text/plain"}, "temporarily unavailable")
        return super().get(url, allow_redirects=allow_redirects, timeout=timeout)


class MissingCanonAuditContentSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        if self.has_cookie or self.headers.get("Authorization", "").startswith("Bearer "):
            if not any(url.endswith(suffix) for suffix in ("/cover", "/book", "/read", "/listen", "/video", "/canon-audit")):
                return FakeResponse(
                    200,
                    {"content-type": "text/html"},
                    """
                    <main data-origin-dossier-detail>
                      <article data-story-scene-cover-uses-selected-character-face="true">
                        <img src="https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/cover" alt="Fitted Origin Dossier cover art for Kestrel">
                      </article>
                      <a href="#origin-edition-read">Read</a>
                      <a href="#origin-edition-portraits">Portraits</a>
                      <a href="#origin-edition-listen">Listen</a>
                      <a href="#origin-edition-watch">Watch</a>
                      <a href="#origin-edition-canon-audit">Canon notes</a>
                      <section id="origin-edition-read" data-origin-edition-tab="read">Read the ebook</section>
                      <section id="origin-edition-portraits" data-origin-edition-tab="portraits" data-origin-portrait-choice-count="3">Portrait shortlist</section>
                      <section id="origin-edition-listen" data-origin-edition-tab="listen" data-origin-audiobook-voice-count="3">Listen in Audiobookshelf</section>
                      <section id="origin-edition-watch" data-origin-edition-tab="watch" data-origin-scene-highlight-count="4">Watch selected cinematic scene</section>
                    </main>
                    """,
                )
        return super().get(url, allow_redirects=allow_redirects, timeout=timeout)


class MissingReadSectionSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        response = super().get(url, allow_redirects=allow_redirects, timeout=timeout)
        if response.status_code == 200 and "text/html" in response.headers.get("content-type", ""):
            response.text = response.text.replace('<section id="origin-edition-read" data-origin-edition-tab="read">Read the ebook</section>', "")
            response.content = response.text.encode("utf-8")
        return response


class MissingSelectedFaceCoverMarkerSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        response = super().get(url, allow_redirects=allow_redirects, timeout=timeout)
        if response.status_code == 200 and "text/html" in response.headers.get("content-type", ""):
            response.text = response.text.replace(' data-story-scene-cover-uses-selected-character-face="true"', "")
            response.content = response.text.encode("utf-8")
        return response


class WrongSelectedFaceCoverRouteSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        response = super().get(url, allow_redirects=allow_redirects, timeout=timeout)
        if response.status_code == 200 and "text/html" in response.headers.get("content-type", ""):
            response.text = response.text.replace(
                "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/cover",
                "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/generic-cover",
            )
            response.content = response.text.encode("utf-8")
        return response


class MissingDeployedPublicationIndexSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        if "audiobookshelf.girschele.com/audiobookshelf/share/" in url:
            return FakeResponse(200, {"content-type": "text/html; charset=utf-8"}, "<main>Audiobookshelf share</main>")
        if (
            not self.has_cookie
            and not self.headers.get("Authorization")
            and not self.headers.get("Cookie")
        ):
            return FakeResponse(302, {"location": "/login?next=%2Faccount%2Fwork"})
        return FakeResponse(404, {"content-type": "text/plain"}, "not found")


def test_deployed_probe_fails_closed_without_owner_token(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)
    monkeypatch.setattr(module.requests, "Session", FakeSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)

    assert result["status"] == "blocked"
    assert result["deployedRouteClaimAllowed"] is False
    assert "missing_deployed_owner_session" in result["blockers"]
    assert result["rawSessionTokenExposed"] is False
    assert result["ownerAuth"]["tokenValueStoredInReceipt"] is False
    assert result["all_private_routes_login_protected"] is True
    assert result["unauthenticated_detail_redirect_verified"] is True
    assert result["unauthenticated_read_redirect_verified"] is True
    assert result["unauthenticated_listen_redirect_verified"] is True
    assert result["unauthenticated_book_redirect_verified"] is True
    assert result["unauthenticated_cover_redirect_verified"] is True
    assert result["unauthenticated_video_redirect_verified"] is True
    assert output.is_file()


def test_deployed_probe_accepts_owner_session_token_alias_without_leaking_value(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTH_MODE", raising=False)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN", "secret-owner-session-alias")
    monkeypatch.setattr(module.requests, "Session", FakeSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "pass"
    assert result["ownerAuth"]["mode"] == "cookie"
    assert result["ownerAuth"]["tokenSha256"]
    assert "secret-owner-session-alias" not in serialized


def test_deployed_probe_accepts_cookie_header_without_leaking_value(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_COOKIE_HEADER", "chummer_hub_access_token=secret-cookie-header")
    monkeypatch.setattr(module.requests, "Session", FakeSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "pass"
    assert result["ownerAuth"]["mode"] == "cookie_header"
    assert result["ownerAuth"]["cookieName"] is None
    assert result["ownerAuth"]["tokenSha256"]
    assert "secret-cookie-header" not in serialized
    assert "chummer_hub_access_token=secret-cookie-header" not in serialized


def test_deployed_probe_accepts_authorization_header_without_leaking_value(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER", "Bearer secret-authorization-header")
    monkeypatch.setattr(module.requests, "Session", FakeSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "pass"
    assert result["ownerAuth"]["mode"] == "authorization_header"
    assert result["ownerAuth"]["tokenSha256"]
    assert "secret-authorization-header" not in serialized
    assert "Bearer secret-authorization-header" not in serialized


def test_deployed_probe_main_uses_origin_edition_context_for_default_output(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    seen: dict[str, object] = {}

    def fake_materialize(evidence_root, base_url, project_id, output, env_file=None, context=None):
        seen["evidence_root"] = evidence_root
        seen["base_url"] = base_url
        seen["project_id"] = project_id
        seen["output"] = output
        seen["context"] = context
        payload = {"status": "blocked", "deployedRouteClaimAllowed": False}
        write_path = Path(output)
        write_path.parent.mkdir(parents=True, exist_ok=True)
        write_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(module, "materialize", fake_materialize)
    monkeypatch.setattr(
        "sys.argv",
        [
            "materialize_origin_dossier_deployed_browser_probe.py",
            "--evidence-root",
            str(tmp_path),
            "--project-id",
            "custom-runner",
            "--family-name",
            "Case",
            "--given-name",
            "Ari",
            "--runner-name",
            "Ghost",
            "--base-url",
            "https://staging.chummer.run",
        ],
    )

    assert module.main() == 1
    assert seen["base_url"] == "https://staging.chummer.run"
    assert seen["project_id"] == "custom-runner"
    assert seen["context"].resolved_namespace == "origin.chummer.run/Case/Ari/Ghost"
    assert seen["output"] == tmp_path / "origin.chummer.run/Case/Ari/Ghost/deployed-chummer-browser-probe.receipt.json"


def test_deployed_probe_passes_with_owner_token_and_real_route_shape(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTH_MODE", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_COOKIE_NAME", raising=False)
    monkeypatch.setattr(module.requests, "Session", FakeSession)

    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", tmp_path / "probe.json")
    serialized = (tmp_path / "probe.json").read_text(encoding="utf-8")

    assert result["status"] == "pass"
    assert result["namespace"] == "origin.chummer.run/Varga/Mira/Kestrel"
    assert result["projectId"] == "varga-mira-kestrel"
    assert result["updated_at"]
    assert result["next_action"] == "Inspect deployed route/index/session mismatch and rerun after deployment state is corrected."
    assert result["blocking_reason"] == ""
    assert result["progress"]["passedChecks"] == result["progress"]["totalChecks"]
    assert result["progress"]["blockedChecks"] == []
    assert result["base_url"] == "https://chummer.run"
    assert result["ownerAuth"]["mode"] == "cookie"
    assert result["ownerAuth"]["cookieName"] == "chummer_hub_access_token"
    assert result["ownerAuth"]["tokenSha256"]
    assert "secret-session" not in serialized
    assert result["logged_in_browser_verified"] is True
    assert result["read_gate_verified"] is True
    assert result["chummer_run_listen_gate_verified"] is True
    assert result["portrait_choice_count_verified"] is True
    assert result["audiobook_voice_count_verified"] is True
    assert result["scene_highlight_count_verified"] is True
    assert result["ownerPageCounts"] == {
        "portraitChoices": 3,
        "audiobookVoiceOptions": 3,
        "sceneHighlights": 4,
    }
    assert result["redirect_location_sha256"]["read"] == result["expected_redirect_location_sha256"]["read"]
    assert result["redirect_location_sha256"]["listen"] == result["expected_redirect_location_sha256"]["listen"]
    assert result["audiobook_share_url_trusted"] is True
    assert result["dossier_share_url_trusted"] is True
    assert result["audiobook_share_reachable"] is True
    assert result["dossier_share_reachable"] is True
    assert result["watch_gate_verified"] is True
    assert result["canon_audit_content_verified"] is True
    assert result["canon_audit_route_verified"] is True
    assert result["chummer_canon_owner_visible"] is True
    assert result["provider_created_facts_blocked_visible"] is True
    assert result["canon_privacy_receipts_present"] is True
    assert result["no_fallback_media_verified"] is True
    assert result["watch_artifact_nonempty"] is True
    assert result["cover_artifact_nonempty"] is True
    assert result["book_artifact_nonempty"] is True
    assert result["cover_sha_matches_import"] is True
    assert result["book_sha_matches_import"] is True
    assert result["video_sha_matches_import"] is True
    assert result["response_body_sizes"]["watch"] > 0
    assert result["response_body_sizes"]["cover"] > 0
    assert result["response_body_sizes"]["book"] > 0
    assert result["response_body_sizes"]["canon_audit"] > 0
    assert result["http_statuses"]["canon_audit"] == 200
    assert result["canon_audit_url"] == "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/canon-audit"
    assert result["url_hashes"]["canon_audit"] == hashlib.sha256(result["canon_audit_url"].encode("utf-8")).hexdigest()
    assert result["owner_playback_e2e_verified"] is True
    assert result["local_fixture_artifacts"] is False
    assert result["all_private_routes_login_protected"] is True
    assert result["unauthenticated_detail_redirect_verified"] is True
    assert result["unauthenticated_read_redirect_verified"] is True
    assert result["unauthenticated_listen_redirect_verified"] is True
    assert result["unauthenticated_book_redirect_verified"] is True
    assert result["unauthenticated_cover_redirect_verified"] is True
    assert result["unauthenticated_video_redirect_verified"] is True
    assert result["unauthenticated_canon_audit_redirect_verified"] is True


def test_deployed_probe_prefers_explicit_audiobook_share_over_legacy_share(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(
        tmp_path,
        audiobook_share_url="https://audiobookshelf.girschele.com/audiobookshelf/share/audio",
        legacy_audiobook_share_url="https://evil.example/audiobookshelf/share/audio",
    )
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", FakeSession)

    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", tmp_path / "probe.json")

    assert result["status"] == "pass"
    assert result["audiobookshelf_redirect"] == "https://audiobookshelf.girschele.com/audiobookshelf/share/audio"
    assert result["audiobook_share_url_trusted"] is True
    assert result["chummer_run_listen_gate_verified"] is True


def test_deployed_probe_prefers_explicit_book_hash_over_legacy_ebook_hash(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(
        tmp_path,
        book_sha=hashlib.sha256(FAKE_BOOK_BYTES).hexdigest(),
        legacy_ebook_sha="0" * 64,
    )
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", FakeSession)

    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", tmp_path / "probe.json")

    assert result["status"] == "pass"
    assert result["expected_import_sha256"]["book"] == hashlib.sha256(FAKE_BOOK_BYTES).hexdigest()
    assert result["book_sha_matches_import"] is True


def test_deployed_probe_falls_back_to_legacy_ebook_hash_when_book_hash_is_absent(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(
        tmp_path,
        book_sha="",
        legacy_ebook_sha=hashlib.sha256(FAKE_BOOK_BYTES).hexdigest(),
    )
    payload_path = tmp_path / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["evidence"].pop("bookArtifactSha256", None)
    payload_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", FakeSession)

    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", tmp_path / "probe.json")

    assert result["status"] == "pass"
    assert result["expected_import_sha256"]["book"] == hashlib.sha256(FAKE_BOOK_BYTES).hexdigest()
    assert result["book_sha_matches_import"] is True


def test_deployed_probe_blocks_untrusted_audiobookshelf_share_even_if_redirect_matches(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(
        tmp_path,
        audiobook_share_url="https://evil.example/audiobookshelf/share/audio",
        dossier_share_url="https://audiobookshelf.girschele.com/audiobookshelf/share/book",
    )
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", FakeSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert result["next_action"] == "Inspect deployed route/index/session mismatch and rerun after deployment state is corrected."
    assert "audiobook_share_url_trusted" in result["blocking_reason"]
    assert "audiobook_share_url_trusted" in result["progress"]["blockedChecks"]
    assert result["audiobook_share_url_trusted"] is False
    assert result["dossier_share_url_trusted"] is True
    assert result["audiobook_share_reachable"] is False
    assert result["dossier_share_reachable"] is True
    assert result["owner_playback_e2e_verified"] is False
    assert "audiobook_share_url_trusted" in result["blockers"]
    assert "owner_playback_e2e_verified" in result["blockers"]
    assert "secret-session" not in serialized


def test_deployed_probe_blocks_when_audiobookshelf_share_page_is_unreachable(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", BrokenAudiobookshelfShareSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert result["audiobook_share_url_trusted"] is True
    assert result["audiobook_share_reachable"] is False
    assert result["dossier_share_reachable"] is True
    assert result["owner_playback_e2e_verified"] is False
    assert "audiobook_share_reachable" in result["blockers"]
    assert "audiobook_share_reachable" in result["progress"]["blockedChecks"]
    assert result["http_statuses"]["audiobook_share"] == 503
    assert "secret-session" not in serialized


def test_deployed_probe_blocks_when_read_section_is_missing_even_if_link_exists(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", MissingReadSectionSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)

    assert result["status"] == "blocked"
    assert result["read_section_visible"] is False
    assert result["read_tab_visible"] is False
    assert "read_section_visible" in result["blockers"]
    assert "read_tab_visible" in result["blockers"]
    assert "owner_playback_e2e_verified" in result["blockers"]


def test_deployed_probe_blocks_generic_cover_without_selected_face_marker(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", MissingSelectedFaceCoverMarkerSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)

    assert result["status"] == "blocked"
    assert result["selected_face_cover_marker_visible"] is False
    assert result["selected_face_cover_alt_visible"] is True
    assert result["selected_face_cover_route_visible"] is True
    assert result["selected_face_cover_visible"] is False
    assert "selected_face_cover_marker_visible" in result["blockers"]
    assert "selected_face_cover_visible" in result["blockers"]
    assert "owner_playback_e2e_verified" in result["blockers"]


def test_deployed_probe_blocks_cover_that_is_not_canonical_owner_cover_route(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", WrongSelectedFaceCoverRouteSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)

    assert result["status"] == "blocked"
    assert result["selected_face_cover_marker_visible"] is True
    assert result["selected_face_cover_alt_visible"] is True
    assert result["selected_face_cover_route_visible"] is False
    assert result["selected_face_cover_visible"] is False
    assert "selected_face_cover_route_visible" in result["blockers"]
    assert "selected_face_cover_visible" in result["blockers"]
    assert "owner_playback_e2e_verified" in result["blockers"]


def test_deployed_probe_blocks_when_canon_audit_content_is_missing(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", MissingCanonAuditContentSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert result["canon_audit_tab_visible"] is True
    assert result["canon_audit_content_verified"] is False
    assert result["chummer_canon_owner_visible"] is False
    assert result["provider_created_facts_blocked_visible"] is False
    assert result["owner_playback_e2e_verified"] is False
    assert "canon_audit_content_verified" in result["blockers"]
    assert "canon_audit_content_verified" in result["progress"]["blockedChecks"]
    assert "secret-session" not in serialized


def test_deployed_probe_blocks_if_any_private_artifact_route_is_public_without_login(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", LeakyAnonymousVideoSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert "all_private_routes_login_protected" in result["blocking_reason"]
    assert "unauthenticated_video_redirect_verified" in result["progress"]["blockedChecks"]
    assert result["deployedRouteClaimAllowed"] is False
    assert result["all_private_routes_login_protected"] is False
    assert result["unauthenticated_video_redirect_verified"] is False
    assert "all_private_routes_login_protected" in result["blockers"]
    assert "unauthenticated_video_redirect_verified" in result["blockers"]
    assert "secret-session" not in serialized


def test_deployed_probe_blocks_if_canon_audit_route_is_public_without_login(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", LeakyAnonymousCanonAuditSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert "all_private_routes_login_protected" in result["blocking_reason"]
    assert "unauthenticated_canon_audit_redirect_verified" in result["progress"]["blockedChecks"]
    assert result["deployedRouteClaimAllowed"] is False
    assert result["all_private_routes_login_protected"] is False
    assert result["unauthenticated_canon_audit_redirect_verified"] is False
    assert "all_private_routes_login_protected" in result["blockers"]
    assert "unauthenticated_canon_audit_redirect_verified" in result["blockers"]
    assert "secret-session" not in serialized


def test_deployed_probe_blocks_when_owner_playback_route_fails_even_if_tabs_render(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", BrokenOwnerVideoSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert result["deployedRouteClaimAllowed"] is False
    assert result["watch_tab_visible"] is True
    assert result["watch_gate_verified"] is False
    assert result["owner_playback_e2e_verified"] is False
    assert "watch_gate_verified" in result["blockers"]
    assert "owner_playback_e2e_verified" in result["blockers"]
    assert "secret-session" not in serialized


def test_deployed_probe_blocks_when_owner_video_body_is_empty(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", EmptyOwnerVideoSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert result["watch_gate_verified"] is True
    assert result["watch_artifact_nonempty"] is False
    assert result["owner_playback_e2e_verified"] is False
    assert result["response_body_sizes"]["watch"] == 0
    assert "watch_artifact_nonempty" in result["blockers"]
    assert "watch_artifact_nonempty" in result["progress"]["blockedChecks"]
    assert "secret-session" not in serialized


def test_deployed_probe_blocks_when_owner_video_hash_does_not_match_import(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.setattr(module.requests, "Session", WrongHashOwnerVideoSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert result["watch_artifact_nonempty"] is True
    assert result["video_sha_matches_import"] is False
    assert result["owner_playback_e2e_verified"] is False
    assert result["expected_import_sha256"]["watch"] == hashlib.sha256(FAKE_VIDEO_BYTES).hexdigest()
    assert result["response_sha256"]["watch"] != result["expected_import_sha256"]["watch"]
    assert "video_sha_matches_import" in result["blockers"]
    assert "video_sha_matches_import" in result["progress"]["blockedChecks"]
    assert "secret-session" not in serialized


def test_deployed_probe_points_to_restart_when_state_import_verified_but_route_404(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    branch = tmp_path / "origin.chummer.run" / "Varga" / "Mira" / "Kestrel"
    branch.mkdir(parents=True, exist_ok=True)
    (branch / "deployed-state-import.receipt.json").write_text(
        json.dumps(
            {
                "status": "verified",
                "restartRequiredForExistingContainer": True,
                "publicationIndexSha256": "a" * 64,
                "copiedArtifacts": [{}, {}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-session")
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTH_MODE", raising=False)
    monkeypatch.setattr(module.requests, "Session", MissingDeployedPublicationIndexSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert result["http_statuses"]["owner_detail"] == 404
    assert result["deployedStateImport"]["present"] is True
    assert result["deployedStateImport"]["status"] == "verified"
    assert result["deployedStateImport"]["restartRequiredForExistingContainer"] is True
    assert result["deployedStateImport"]["publicationIndexSha256"] == "a" * 64
    assert result["deployedStateImport"]["copiedArtifactCount"] == 2
    assert result["next_action"] == (
        "Restart/recreate chummer-portal only after explicit deploy approval so "
        "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=/app/state/origin-dossier-publications.json "
        "is active, then rerun this probe."
    )
    assert "secret-session" not in serialized


def test_deployed_probe_supports_bearer_auth_mode_without_storing_token(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", "secret-bearer-session")
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_AUTH_MODE", "bearer")
    monkeypatch.setattr(module.requests, "Session", FakeSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "pass"
    assert result["ownerAuth"]["mode"] == "bearer"
    assert result["ownerAuth"]["cookieName"] is None
    assert result["ownerAuth"]["tokenSha256"]
    assert result["ownerAuth"]["tokenValueStoredInReceipt"] is False
    assert "secret-bearer-session" not in serialized


def test_deployed_probe_loads_scoped_env_file_without_storing_values(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTH_MODE", raising=False)
    monkeypatch.setattr(module.requests, "Session", FakeSession)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN=secret-from-env-file",
                "CHUMMER_DEPLOYED_E2E_AUTH_MODE=bearer",
                "UNRELATED_SECRET=must_not_load",
            ]
        ),
        encoding="utf-8",
    )

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output, env_file)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "pass"
    assert result["ownerAuth"]["mode"] == "bearer"
    assert result["envFile"]["provided"] is True
    assert result["envFile"]["loadedKeys"] == [
        "CHUMMER_DEPLOYED_E2E_AUTH_MODE",
        "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN",
    ]
    assert result["envFile"]["valuesStoredInReceipt"] is False
    assert "secret-from-env-file" not in serialized
    assert "must_not_load" not in serialized
