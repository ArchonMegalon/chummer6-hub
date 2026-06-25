from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_origin_dossier_deployed_browser_probe.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_dossier_deployed_browser_probe_verifier", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def module_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def probe_payload(*, status: str = "blocked") -> dict:
    passed = status == "pass"
    blockers = [] if passed else ["missing_deployed_identity_token", "owner_playback_e2e_verified"]
    cover_sha = "b" * 64
    book_sha = "c" * 64
    video_sha = "d" * 64
    flags = {
        "logged_in_browser_verified": passed,
        "selected_face_cover_marker_visible": passed,
        "selected_face_cover_alt_visible": passed,
        "selected_face_cover_route_visible": passed,
        "selected_face_cover_visible": passed,
        "read_tab_visible": passed,
        "read_section_visible": passed,
        "listen_tab_visible": passed,
        "listen_section_visible": passed,
        "watch_tab_visible": passed,
        "watch_section_visible": passed,
        "canon_audit_tab_visible": passed,
        "canon_audit_section_visible": passed,
        "chummer_canon_owner_visible": passed,
        "provider_created_facts_blocked_visible": passed,
        "canon_privacy_receipts_present": passed,
        "no_fallback_media_verified": passed,
        "canon_audit_content_verified": passed,
        "read_gate_verified": passed,
        "chummer_run_listen_gate_verified": passed,
        "watch_gate_verified": passed,
        "cover_route_verified": passed,
        "book_route_verified": passed,
        "watch_artifact_nonempty": passed,
        "cover_artifact_nonempty": passed,
        "book_artifact_nonempty": passed,
        "cover_sha_matches_import": passed,
        "book_sha_matches_import": passed,
        "video_sha_matches_import": passed,
        "audiobook_share_url_trusted": passed,
        "dossier_share_url_trusted": passed,
        "audiobook_share_reachable": passed,
        "dossier_share_reachable": passed,
        "owner_playback_e2e_verified": passed,
        "unauthenticated_detail_redirect_verified": True,
        "unauthenticated_read_redirect_verified": True,
        "unauthenticated_listen_redirect_verified": True,
        "unauthenticated_book_redirect_verified": True,
        "unauthenticated_cover_redirect_verified": True,
        "unauthenticated_video_redirect_verified": True,
        "all_private_routes_login_protected": True,
    }
    return {
        "contractName": "chummer.origin_edition.deployed_browser_probe.v1",
        "status": status,
        "base_url": "https://chummer.run",
        "projectId": "varga-mira-kestrel",
        "owner_detail_page": "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel",
        "selected_face_cover_url": "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/cover",
        "read_url": "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/read",
        "book_url": "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/book",
        "listen_url": "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/listen",
        "watch_url": "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/video",
        "audiobookshelf_redirect": "https://audiobookshelf.girschele.com/audiobookshelf/share/audio",
        "audiobookshelf_dossier_redirect": "https://audiobookshelf.girschele.com/audiobookshelf/share/book",
        "updated_at": "2026-06-25T13:00:00Z",
        "next_action": "Inspect deployed route/index/session mismatch and rerun after deployment state is corrected." if passed else "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN for a real deployed owner session and rerun this probe.",
        "blocking_reason": "" if passed else ",".join(blockers),
        "goldEligible": passed,
        "deployedRouteClaimAllowed": passed,
        "local_fixture_artifacts": False,
        "live_provider_artifacts_verified": True,
        "live_provider_delivery_verified": True,
        "rawCredentialExposed": False,
        "rawSessionTokenExposed": False,
        "ownerAuth": {
            "mode": "cookie",
            "cookieName": "chummer_hub_access_token",
            "tokenSha256": "a" * 64 if passed else "",
            "tokenValueStoredInReceipt": False,
        },
        "envFile": {"valuesStoredInReceipt": False},
        "blockers": blockers,
        "progress": {
            "passedChecks": len([value for value in flags.values() if value]),
            "totalChecks": len(flags),
            "blockedChecks": [key for key, value in flags.items() if not value],
        },
        "url_hashes": {
            "owner": module_sha256("https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel"),
            "read": module_sha256("https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/read"),
            "book": module_sha256("https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/book"),
            "listen": module_sha256("https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/listen"),
            "watch": module_sha256("https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/video"),
            "cover": module_sha256("https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/cover"),
            "audiobookshelf_redirect": module_sha256("https://audiobookshelf.girschele.com/audiobookshelf/share/audio"),
            "audiobookshelf_dossier_redirect": module_sha256("https://audiobookshelf.girschele.com/audiobookshelf/share/book"),
        },
        "response_sha256": {
            "cover": cover_sha if passed else "",
            "book": book_sha if passed else "",
            "watch": video_sha if passed else "",
        },
        "redirect_location_sha256": {
            "read": module_sha256("https://audiobookshelf.girschele.com/audiobookshelf/share/book") if passed else "",
            "listen": module_sha256("https://audiobookshelf.girschele.com/audiobookshelf/share/audio") if passed else "",
        },
        "expected_redirect_location_sha256": {
            "read": module_sha256("https://audiobookshelf.girschele.com/audiobookshelf/share/book"),
            "listen": module_sha256("https://audiobookshelf.girschele.com/audiobookshelf/share/audio"),
        },
        "response_body_sizes": {
            "cover": 10 if passed else 0,
            "book": 10 if passed else 0,
            "watch": 10 if passed else 0,
            "audiobook_share": 100 if passed else 0,
            "dossier_share": 100 if passed else 0,
        },
        "http_statuses": {
            "cover": 200 if passed else None,
            "book": 200 if passed else None,
            "watch": 200 if passed else None,
            "read": 302 if passed else None,
            "listen": 302 if passed else None,
            "audiobook_share": 200 if passed else None,
            "dossier_share": 200 if passed else None,
        },
        "expected_import_sha256": {
            "cover": cover_sha,
            "book": book_sha,
            "watch": video_sha,
        },
        **flags,
    }


def test_verifier_accepts_token_missing_blocked_probe_with_private_routes_protected(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    write_json(path, probe_payload())

    ok, issues = module.verify(path)

    assert ok is True
    assert issues == []


def test_verifier_accepts_pass_probe_when_require_pass(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    write_json(path, probe_payload(status="pass"))

    ok, issues = module.verify(path, require_pass=True)

    assert ok is True
    assert issues == []


def test_verifier_rejects_public_private_artifact_route(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload()
    payload["unauthenticated_video_redirect_verified"] = False
    payload["all_private_routes_login_protected"] = False
    write_json(path, payload)

    ok, issues = module.verify(path)

    assert ok is False
    assert "private_route_flag_not_true:unauthenticated_video_redirect_verified" in issues
    assert "private_route_flag_not_true:all_private_routes_login_protected" in issues


def test_verifier_rejects_pass_probe_with_missing_owner_playback_flag(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["owner_playback_e2e_verified"] = False
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "pass_flag_not_true:owner_playback_e2e_verified" in issues
    assert "pass_probe_owner_playback_not_verified" in issues


def test_verifier_rejects_pass_probe_with_empty_owner_video_artifact(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["watch_artifact_nonempty"] = False
    payload["response_body_sizes"]["watch"] = 0
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "pass_flag_not_true:watch_artifact_nonempty" in issues
    assert "pass_probe_empty_response_body:watch" in issues


def test_verifier_rejects_nonempty_flag_without_response_body_size(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["response_body_sizes"]["book"] = 0
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "nonempty_flag_not_backed_by_body_size:book" in issues
    assert "pass_probe_empty_response_body:book" in issues


def test_verifier_rejects_share_reachable_flag_without_http_evidence(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["http_statuses"]["audiobook_share"] = 503
    payload["response_body_sizes"]["audiobook_share"] = 0
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "share_reachable_flag_not_backed_by_status:audiobook_share" in issues
    assert "share_reachable_flag_not_backed_by_body_size:audiobook_share" in issues
    assert "pass_probe_share_status_not_200:audiobook_share" in issues
    assert "pass_probe_share_body_empty:audiobook_share" in issues


def test_verifier_rejects_route_flag_without_http_status(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["http_statuses"]["cover"] = 404
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "route_flag_not_backed_by_status:cover" in issues


def test_verifier_rejects_read_gate_without_redirect_status(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["http_statuses"]["read"] = 200
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "redirect_gate_flag_not_backed_by_status:read" in issues


def test_verifier_rejects_listen_gate_without_expected_redirect_location(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["redirect_location_sha256"]["listen"] = "0" * 64
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "redirect_gate_flag_not_backed_by_location:listen" in issues
    assert "pass_probe_redirect_location_mismatch:listen" in issues


def test_verifier_rejects_pass_probe_with_missing_canon_audit_content(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["canon_audit_content_verified"] = False
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "pass_flag_not_true:canon_audit_content_verified" in issues


def test_verifier_rejects_pass_probe_with_mismatched_video_hash(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["video_sha_matches_import"] = False
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "pass_flag_not_true:video_sha_matches_import" in issues


def test_verifier_rejects_hash_match_flag_not_backed_by_response_hash(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["response_sha256"]["watch"] = "0" * 64
    payload["video_sha_matches_import"] = True
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "artifact_hash_match_flag_not_backed:watch" in issues
    assert "pass_probe_artifact_hash_mismatch:watch" in issues


def test_verifier_rejects_matching_hash_when_match_flag_false(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["book_sha_matches_import"] = False
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "artifact_hashes_match_but_flag_false:book" in issues
    assert "pass_flag_not_true:book_sha_matches_import" in issues


def test_verifier_rejects_missing_normalized_status_contract(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload()
    payload.pop("next_action")
    payload.pop("blocking_reason")
    write_json(path, payload)

    ok, issues = module.verify(path)

    assert ok is False
    assert "next_action_missing" in issues
    assert "blocked_probe_missing_blocking_reason" in issues


def test_verifier_rejects_route_hash_that_does_not_match_declared_project(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["url_hashes"]["read"] = "0" * 64
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "url_hash_mismatch:read" in issues
    assert "raw_route_hash_mismatch:read_url" in issues


def test_verifier_rejects_raw_route_that_does_not_match_declared_project(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["read_url"] = "https://chummer.run/account/work/origin-dossiers/other/read"
    payload["url_hashes"]["read"] = module_sha256(payload["read_url"])
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "url_hash_mismatch:read" in issues
    assert "raw_route_mismatch:read_url" in issues


def test_verifier_rejects_raw_audiobookshelf_share_hash_mismatch(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    payload = probe_payload(status="pass")
    payload["audiobookshelf_redirect"] = "https://audiobookshelf.girschele.com/audiobookshelf/share/changed"
    write_json(path, payload)

    ok, issues = module.verify(path, require_pass=True)

    assert ok is False
    assert "raw_share_hash_mismatch:audiobookshelf_redirect" in issues


def test_verifier_rejects_secret_marker_even_when_json_invalid(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    write_json(path, probe_payload())
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\nBearer leaked\napi.telegram.org/bot123\nsecret-session\nUNMIXR_API_KEY=leaked\n",
        encoding="utf-8",
    )

    ok, issues = module.verify(path)

    assert ok is False
    assert "forbidden_secret_marker:Bearer " in issues
    assert "forbidden_secret_marker:api.telegram.org/bot" in issues
    assert "forbidden_secret_marker:secret-session" in issues
    assert "forbidden_secret_marker:UNMIXR_API_KEY=" in issues
    assert any(issue.startswith("invalid_json:") for issue in issues)


def test_default_probe_path_uses_origin_edition_env_context(monkeypatch, tmp_path: Path) -> None:
    module = load_module()
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_EVIDENCE_ROOT", str(tmp_path))
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_PROJECT_ID", "case-ari-ghost")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_FAMILY_NAME", "Case")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_GIVEN_NAME", "Ari")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_RUNNER_NAME", "Ghost")
    monkeypatch.delenv("CHUMMER_ORIGIN_EDITION_NAMESPACE", raising=False)

    assert module.deployed_browser_probe_from_env() == (
        tmp_path / "origin.chummer.run/Case/Ari/Ghost/deployed-chummer-browser-probe.receipt.json"
    )
