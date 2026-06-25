from __future__ import annotations

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


def probe_payload(*, status: str = "blocked") -> dict:
    passed = status == "pass"
    blockers = [] if passed else ["missing_deployed_identity_token", "owner_playback_e2e_verified"]
    flags = {
        "logged_in_browser_verified": passed,
        "selected_face_cover_visible": passed,
        "read_tab_visible": passed,
        "listen_tab_visible": passed,
        "watch_tab_visible": passed,
        "canon_audit_tab_visible": passed,
        "read_gate_verified": passed,
        "chummer_run_listen_gate_verified": passed,
        "watch_gate_verified": passed,
        "cover_route_verified": passed,
        "book_route_verified": passed,
        "audiobook_share_url_trusted": passed,
        "dossier_share_url_trusted": passed,
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
            "owner": "a" * 64,
            "read": "b" * 64,
            "book": "c" * 64,
            "listen": "d" * 64,
            "watch": "e" * 64,
            "cover": "f" * 64,
            "audiobookshelf_redirect": "1" * 64,
            "audiobookshelf_dossier_redirect": "2" * 64,
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


def test_verifier_rejects_secret_marker_even_when_json_invalid(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "probe.json"
    write_json(path, probe_payload())
    path.write_text(path.read_text(encoding="utf-8") + "\nBearer leaked\n", encoding="utf-8")

    ok, issues = module.verify(path)

    assert ok is False
    assert "forbidden_secret_marker:Bearer " in issues
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
