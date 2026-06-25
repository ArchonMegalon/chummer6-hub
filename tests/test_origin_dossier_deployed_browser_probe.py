from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_dossier_deployed_browser_probe.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_dossier_deployed_browser_probe", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_import_request(
    root: Path,
    *,
    audiobook_share_url: str = "https://audiobookshelf.girschele.com/audiobookshelf/share/audio",
    dossier_share_url: str = "https://audiobookshelf.girschele.com/audiobookshelf/share/book",
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json").write_text(
        json.dumps(
            {
                "importRequest": {
                    "audiobookshelfShareUrl": audiobook_share_url,
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
        if not self.has_cookie and not self.headers.get("Authorization", "").startswith("Bearer "):
            return FakeResponse(302, {"location": "/login?next=%2Faccount%2Fwork"})
        if url.endswith("/cover"):
            return FakeResponse(200, {"content-type": "image/jpeg"}, content=b"\xff\xd8cover-bytes")
        if url.endswith("/book"):
            return FakeResponse(200, {"content-type": "application/epub+zip"}, content=b"PK\x03\x04ebook-bytes")
        if url.endswith("/read"):
            return FakeResponse(302, {"location": "https://audiobookshelf.girschele.com/audiobookshelf/share/book"})
        if url.endswith("/listen"):
            return FakeResponse(302, {"location": "https://audiobookshelf.girschele.com/audiobookshelf/share/audio"})
        if url.endswith("/video"):
            return FakeResponse(200, {"content-type": "video/mp4"}, content=b"\x00\x00\x00\x18ftypmp42movie-bytes")
        return FakeResponse(
            200,
            {"content-type": "text/html"},
            """
            <main data-origin-dossier-detail>
              <img alt="Rendered Origin Dossier story scene cover for Kestrel">
              <a href="#origin-edition-read">Read</a>
              <a href="#origin-edition-listen">Listen</a>
              <a href="#origin-edition-watch">Watch</a>
              <a href="#origin-edition-canon-audit">Canon Audit</a>
            </main>
            """,
        )


class LeakyAnonymousVideoSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        if not self.has_cookie and not self.headers.get("Authorization", "").startswith("Bearer ") and url.endswith("/video"):
            return FakeResponse(200, {"content-type": "video/mp4"})
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


class BrokenAudiobookshelfShareSession(FakeSession):
    def get(self, url: str, *, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        if "audiobookshelf.girschele.com/audiobookshelf/share/audio" in url:
            return FakeResponse(503, {"content-type": "text/plain"}, "temporarily unavailable")
        return super().get(url, allow_redirects=allow_redirects, timeout=timeout)


def test_deployed_probe_fails_closed_without_owner_token(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    write_import_request(tmp_path)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)
    monkeypatch.setattr(module.requests, "Session", FakeSession)

    output = tmp_path / "probe.json"
    result = module.materialize(tmp_path, "https://chummer.run", "varga-mira-kestrel", output)

    assert result["status"] == "blocked"
    assert result["deployedRouteClaimAllowed"] is False
    assert "missing_deployed_identity_token" in result["blockers"]
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
    assert result["audiobook_share_url_trusted"] is True
    assert result["dossier_share_url_trusted"] is True
    assert result["audiobook_share_reachable"] is True
    assert result["dossier_share_reachable"] is True
    assert result["watch_gate_verified"] is True
    assert result["watch_artifact_nonempty"] is True
    assert result["cover_artifact_nonempty"] is True
    assert result["book_artifact_nonempty"] is True
    assert result["response_body_sizes"]["watch"] > 0
    assert result["response_body_sizes"]["cover"] > 0
    assert result["response_body_sizes"]["book"] > 0
    assert result["owner_playback_e2e_verified"] is True
    assert result["local_fixture_artifacts"] is False
    assert result["all_private_routes_login_protected"] is True
    assert result["unauthenticated_detail_redirect_verified"] is True
    assert result["unauthenticated_read_redirect_verified"] is True
    assert result["unauthenticated_listen_redirect_verified"] is True
    assert result["unauthenticated_book_redirect_verified"] is True
    assert result["unauthenticated_cover_redirect_verified"] is True
    assert result["unauthenticated_video_redirect_verified"] is True


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
