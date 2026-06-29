from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "audit_origin_dossier_gold_e2e.py"
IMPORT_SCRIPT = ROOT / "scripts" / "materialize_origin_dossier_live_import_request.py"
LIVE_IMPORT_TEST = ROOT / "tests" / "test_origin_dossier_live_import_request.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_live_import_request(tmp_path: Path) -> tuple[Path, dict[str, Path | str]]:
    fixture_module = load_module(LIVE_IMPORT_TEST, "origin_dossier_live_import_fixture")
    import_module = load_module(IMPORT_SCRIPT, "origin_dossier_live_import_script")
    manifest, paths = fixture_module.build_valid_fixture(tmp_path)
    paths["shareUrl"] = paths["audiobookShareUrl"]
    output = tmp_path / "live-import.generated.json"
    import_module.materialize(manifest, output)
    return output, paths


def write_browser_proof(root: Path, *, project_id: str, share_url: str, live: bool = True) -> Path:
    base_url = "https://chummer.run" if live else "http://127.0.0.1:53411"
    return write_json(
        root / "browser-proof.json",
        {
            "generated_at_utc": now_iso(),
            "status": "pass",
            "proof_scope": "deployed_authenticated_chummer_run_live_origin_dossier_proof"
            if live
            else "authenticated_chummer_run_route_proof",
            "local_fixture_artifacts": not live,
            "live_provider_artifacts_verified": live,
            "live_provider_delivery_verified": live,
            "project_id": project_id,
            "base_url": base_url,
            "owner_account_page": f"{base_url}/account/work#origin-dossier-library",
            "owner_detail_page": f"{base_url}/account/work/origin-dossiers/{project_id}",
            "selected_face_cover_url": f"{base_url}/account/work/origin-dossiers/{project_id}/cover",
            "read_url": f"{base_url}/account/work/origin-dossiers/{project_id}/read",
            "book_url": f"{base_url}/account/work/origin-dossiers/{project_id}/book",
            "listen_url": f"{base_url}/account/work/origin-dossiers/{project_id}/listen",
            "watch_url": f"{base_url}/account/work/origin-dossiers/{project_id}/video",
            "canon_audit_url": f"{base_url}/account/work/origin-dossiers/{project_id}/canon-audit",
            "audiobookshelf_redirect": share_url,
            "logged_in_browser_verified": True,
            "selected_face_cover_visible": True,
            "read_tab_visible": True,
            "listen_tab_visible": True,
            "watch_tab_visible": True,
            "canon_audit_tab_visible": True,
            "canon_audit_content_verified": True,
            "canon_audit_route_verified": True,
            "read_gate_verified": True,
            "chummer_run_listen_gate_verified": True,
            "watch_gate_verified": True,
            "unauthenticated_detail_redirect_verified": True,
            "unauthenticated_read_redirect_verified": True,
            "unauthenticated_listen_redirect_verified": True,
            "unauthenticated_book_redirect_verified": True,
            "unauthenticated_cover_redirect_verified": True,
            "unauthenticated_video_redirect_verified": True,
            "unauthenticated_canon_audit_redirect_verified": True,
            "all_private_routes_login_protected": True,
            "owner_playback_e2e_verified": live,
        },
    )


def write_deployed_probe(root: Path, *, project_id: str, share_url: str, status: str = "blocked") -> Path:
    passed = status == "pass"
    return write_json(
        root / "deployed-browser-probe.json",
        {
            "contractName": "chummer.origin_edition.deployed_browser_probe.v1",
            "generated_at_utc": now_iso(),
            "status": status,
            "project_id": project_id,
            "base_url": "https://chummer.run",
            "owner_account_page": "https://chummer.run/account/work#origin-dossier-library",
            "owner_detail_page": f"https://chummer.run/account/work/origin-dossiers/{project_id}",
            "selected_face_cover_url": f"https://chummer.run/account/work/origin-dossiers/{project_id}/cover",
            "read_url": f"https://chummer.run/account/work/origin-dossiers/{project_id}/read",
            "book_url": f"https://chummer.run/account/work/origin-dossiers/{project_id}/book",
            "listen_url": f"https://chummer.run/account/work/origin-dossiers/{project_id}/listen",
            "watch_url": f"https://chummer.run/account/work/origin-dossiers/{project_id}/video",
            "canon_audit_url": f"https://chummer.run/account/work/origin-dossiers/{project_id}/canon-audit",
            "audiobookshelf_redirect": share_url,
            "local_fixture_artifacts": False,
            "deployedRouteClaimAllowed": passed,
            "live_provider_artifacts_verified": True,
            "live_provider_delivery_verified": True,
            "logged_in_browser_verified": passed,
            "selected_face_cover_visible": passed,
            "read_tab_visible": passed,
            "listen_tab_visible": passed,
            "watch_tab_visible": passed,
            "canon_audit_tab_visible": passed,
            "canon_audit_content_verified": passed,
            "canon_audit_route_verified": passed,
            "read_gate_verified": passed,
            "chummer_run_listen_gate_verified": passed,
            "watch_gate_verified": passed,
            "unauthenticated_detail_redirect_verified": True,
            "unauthenticated_read_redirect_verified": True,
            "unauthenticated_listen_redirect_verified": True,
            "unauthenticated_book_redirect_verified": True,
            "unauthenticated_cover_redirect_verified": True,
            "unauthenticated_video_redirect_verified": True,
            "unauthenticated_canon_audit_redirect_verified": True,
            "all_private_routes_login_protected": True,
            "owner_playback_e2e_verified": passed,
            "blockers": [] if passed else ["missing_deployed_identity_token", "logged_in_browser_verified"],
        },
    )


def write_deployed_operator_handoff(root: Path, *, status: str = "ready_for_operator_token", leak: bool = False) -> Path:
    payload = {
        "contractName": "chummer.origin_edition.deployed_operator_handoff.v1",
        "generatedAtUtc": now_iso(),
        "status": status,
        "goldEligible": status == "pass",
        "goalCompletionClaimAllowed": False,
        "blockers": [] if status == "pass" else ["missing_deployed_identity_token", "deployed_browser_probe_not_pass"],
        "requiredEnv": {
            "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN": {
                "required": True,
                "presentInCurrentProcess": status == "pass",
                "valueStoredInReceipt": False,
            }
        },
        "privacy": {
            "rawCredentialExposed": False,
            "rawSessionTokenExposed": leak,
            "envValuesExposed": False,
            "deploymentPerformed": False,
        },
    }
    if leak:
        payload["debug"] = "telegram_bot_token"
    return write_json(root / "deployed-operator-handoff.receipt.json", payload)


def test_gold_e2e_audit_passes_only_when_live_import_ea_delivery_and_deployed_browser_proof_pass(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit")
    live_import, paths = build_live_import_request(tmp_path)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url=str(paths["shareUrl"]),
        live=True,
    )

    result = audit_module.audit(
        live_import_request=live_import,
        ea_delivery_receipt=Path(paths["eaLiveReceipt"]),
        browser_proof=browser_proof,
        output=tmp_path / "audit.json",
    )

    assert result["status"] == "pass"
    assert result["finalVerdict"] == "ORIGIN_DOSSIER_GOLD_READY"
    assert result["goalCompletionClaimAllowed"] is True
    assert result["failedCodes"] == []


def test_gold_e2e_audit_records_operator_handoff_without_requiring_handoff_pass(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_handoff_advisory")
    live_import, paths = build_live_import_request(tmp_path)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url=str(paths["shareUrl"]),
        live=True,
    )
    handoff = write_deployed_operator_handoff(tmp_path)

    result = audit_module.audit(
        live_import_request=live_import,
        ea_delivery_receipt=Path(paths["eaLiveReceipt"]),
        browser_proof=browser_proof,
        deployed_operator_handoff=handoff,
    )

    assert result["status"] == "pass"
    assert result["failedCodes"] == []
    assert result["evidence"]["deployed_operator_handoff"]["status"] == "ready_for_operator_token"
    assert "missing_deployed_identity_token" in result["evidence"]["deployed_operator_handoff"]["blockers"]
    assert result["evidence"]["deployed_operator_handoff"]["required_env_present"] is False


def test_gold_e2e_audit_blocks_operator_handoff_secret_leak(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_handoff_leak")
    live_import, paths = build_live_import_request(tmp_path)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url=str(paths["shareUrl"]),
        live=True,
    )
    handoff = write_deployed_operator_handoff(tmp_path, leak=True)

    result = audit_module.audit(
        live_import_request=live_import,
        ea_delivery_receipt=Path(paths["eaLiveReceipt"]),
        browser_proof=browser_proof,
        deployed_operator_handoff=handoff,
    )

    assert result["status"] == "blocked"
    assert "deployed_operator_handoff_raw_session_token_exposed" in result["failedCodes"]
    assert "deployed_operator_handoff_raw_secret_or_path_leak" in result["failedCodes"]


def test_gold_e2e_audit_reports_deployed_probe_blockers(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_deployed_probe_blocked")
    live_import, paths = build_live_import_request(tmp_path)
    browser_proof = write_deployed_probe(
        tmp_path,
        project_id="origin-live-gold",
        share_url=str(paths["shareUrl"]),
        status="blocked",
    )

    result = audit_module.audit(
        live_import_request=live_import,
        ea_delivery_receipt=Path(paths["eaLiveReceipt"]),
        browser_proof=browser_proof,
    )

    assert result["status"] == "blocked"
    assert "browser_proof_not_pass" in result["failedCodes"]
    assert "browser_deployed_route_claim_not_allowed" in result["failedCodes"]
    assert "browser_deployed_probe_blocked:missing_deployed_identity_token" in result["failedCodes"]
    assert "browser_deployed_probe_blocked:logged_in_browser_verified" in result["failedCodes"]
    assert result["evidence"]["browser_proof"]["deployed_route_claim_allowed"] is False


def test_gold_e2e_audit_blocks_local_fixture_browser_proof(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_local")
    live_import, paths = build_live_import_request(tmp_path)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url=str(paths["shareUrl"]),
        live=False,
    )

    result = audit_module.audit(
        live_import_request=live_import,
        ea_delivery_receipt=Path(paths["eaLiveReceipt"]),
        browser_proof=browser_proof,
    )

    assert result["status"] == "blocked"
    assert "browser_proof_is_local_fixture" in result["failedCodes"]
    assert "browser_base_url_not_deployed_chummer_run" in result["failedCodes"]
    assert result["goalCompletionClaimAllowed"] is False


def test_gold_e2e_audit_blocks_missing_live_ea_delivery(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_ea")
    live_import, paths = build_live_import_request(tmp_path)
    delivery_path = Path(paths["eaLiveReceipt"])
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    delivery["status"] = "blocked"
    delivery["live_delivery_claim_allowed"] = False
    delivery["failed_codes"] = ["valid_live_audiobook_delivery_missing"]
    write_json(delivery_path, delivery)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url=str(paths["shareUrl"]),
        live=True,
    )

    result = audit_module.audit(
        live_import_request=live_import,
        ea_delivery_receipt=delivery_path,
        browser_proof=browser_proof,
    )

    assert result["status"] == "blocked"
    assert "ea_delivery_not_pass" in result["failedCodes"]
    assert "ea_live_delivery_claim_not_allowed" in result["failedCodes"]
    assert "ea_delivery_failed_codes_present" in result["failedCodes"]


def test_gold_e2e_audit_blocks_telegram_delivery_without_origin_link_bundle(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_missing_origin_links")
    live_import, paths = build_live_import_request(tmp_path)
    delivery_path = Path(paths["eaLiveReceipt"])
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    delivery["selected_delivery"].pop("origin_edition_link_bundle", None)
    write_json(delivery_path, delivery)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url=str(paths["shareUrl"]),
        live=True,
    )

    result = audit_module.audit(
        live_import_request=live_import,
        ea_delivery_receipt=delivery_path,
        browser_proof=browser_proof,
    )

    assert result["status"] == "blocked"
    assert "ea_origin_link_bundle_not_sent" in result["failedCodes"]
    assert "ea_origin_link_bundle_missing_required_links" in result["failedCodes"]
    assert "ea_origin_link_bundle_hash_mismatch:read_url_sha256" in result["failedCodes"]


def test_gold_e2e_audit_blocks_live_import_without_m4b_provider_gate_evidence(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_missing_m4b_provider_gate")
    live_import, paths = build_live_import_request(tmp_path)
    payload = json.loads(live_import.read_text(encoding="utf-8"))
    payload["evidence"].pop("eaM4bProviderImportReceiptSha256", None)
    payload["importRequest"].pop("m4bProviderImportReceiptPath", None)
    write_json(live_import, payload)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url=str(paths["shareUrl"]),
        live=True,
    )

    result = audit_module.audit(
        live_import_request=live_import,
        ea_delivery_receipt=Path(paths["eaLiveReceipt"]),
        browser_proof=browser_proof,
    )

    assert result["status"] == "blocked"
    assert "live_import_evidence_hash_missing:eaM4bProviderImportReceiptSha256" in result["failedCodes"]
    assert "import_artifact_missing:m4bProviderImportReceiptPath" in result["failedCodes"]


def test_gold_e2e_audit_blocks_live_import_without_humanizer_quality_evidence(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_missing_humanizer_quality")
    live_import, paths = build_live_import_request(tmp_path)
    payload = json.loads(live_import.read_text(encoding="utf-8"))
    payload["evidence"].pop("humanizerQualityReceiptSha256", None)
    payload["importRequest"].pop("humanizerQualityReceiptPath", None)
    write_json(live_import, payload)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url=str(paths["shareUrl"]),
        live=True,
    )

    result = audit_module.audit(
        live_import_request=live_import,
        ea_delivery_receipt=Path(paths["eaLiveReceipt"]),
        browser_proof=browser_proof,
    )

    assert result["status"] == "blocked"
    assert "live_import_evidence_hash_missing:humanizerQualityReceiptSha256" in result["failedCodes"]
    assert "import_artifact_missing:humanizerQualityReceiptPath" in result["failedCodes"]


def test_gold_e2e_audit_accepts_live_audiobookshelf_host_but_blocks_share_mismatch(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_live_host_mismatch")
    live_import, paths = build_live_import_request(tmp_path)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url="https://audiobookshelf.girschele.com/audiobookshelf/share/origin-live-gold",
        live=True,
    )

    result = audit_module.audit(
        live_import_request=live_import,
        ea_delivery_receipt=Path(paths["eaLiveReceipt"]),
        browser_proof=browser_proof,
    )

    assert result["status"] == "blocked"
    assert "browser_audiobookshelf_redirect_mismatch" in result["failedCodes"]
    assert "browser_audiobookshelf_redirect_untrusted" not in result["failedCodes"]


def test_gold_e2e_audit_blocks_untrusted_browser_playback_redirect(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_untrusted")
    live_import, paths = build_live_import_request(tmp_path)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url="https://evil.example/share/origin-live-gold",
        live=True,
    )

    result = audit_module.audit(
        live_import_request=live_import,
        ea_delivery_receipt=Path(paths["eaLiveReceipt"]),
        browser_proof=browser_proof,
    )

    assert result["status"] == "blocked"
    assert "browser_audiobookshelf_redirect_mismatch" in result["failedCodes"]
    assert "browser_audiobookshelf_redirect_untrusted" in result["failedCodes"]


def test_gold_e2e_audit_blocks_incomplete_browser_tab_and_auth_proof(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_incomplete_browser")
    live_import, paths = build_live_import_request(tmp_path)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url=str(paths["shareUrl"]),
        live=True,
    )
    payload = json.loads(browser_proof.read_text(encoding="utf-8"))
    payload["watch_tab_visible"] = False
    payload["canon_audit_tab_visible"] = False
    payload["canon_audit_content_verified"] = False
    payload["canon_audit_route_verified"] = False
    payload["unauthenticated_video_redirect_verified"] = False
    payload["unauthenticated_canon_audit_redirect_verified"] = False
    payload["all_private_routes_login_protected"] = False
    payload["watch_url"] = ""
    payload["canon_audit_url"] = ""
    write_json(browser_proof, payload)

    result = audit_module.audit(
        live_import_request=live_import,
        ea_delivery_receipt=Path(paths["eaLiveReceipt"]),
        browser_proof=browser_proof,
    )

    assert result["status"] == "blocked"
    assert "browser_flag_missing:watch_tab_visible" in result["failedCodes"]
    assert "browser_flag_missing:canon_audit_tab_visible" in result["failedCodes"]
    assert "browser_flag_missing:canon_audit_content_verified" in result["failedCodes"]
    assert "browser_flag_missing:canon_audit_route_verified" in result["failedCodes"]
    assert "browser_flag_missing:unauthenticated_video_redirect_verified" in result["failedCodes"]
    assert "browser_flag_missing:unauthenticated_canon_audit_redirect_verified" in result["failedCodes"]
    assert "browser_flag_missing:all_private_routes_login_protected" in result["failedCodes"]
    assert "browser_watch_url_not_chummer_run" in result["failedCodes"]
    assert "browser_canon_audit_url_not_chummer_run" in result["failedCodes"]


def test_gold_e2e_audit_reports_missing_live_import_request_as_specific_blocker(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_missing_import")
    _live_import, paths = build_live_import_request(tmp_path)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url=str(paths["shareUrl"]),
        live=True,
    )

    result = audit_module.audit(
        live_import_request=tmp_path / "missing-live-import.json",
        ea_delivery_receipt=Path(paths["eaLiveReceipt"]),
        browser_proof=browser_proof,
    )

    assert result["status"] == "blocked"
    assert "live_import_request_missing" in result["failedCodes"]
    assert "ea_delivery_not_audited_without_live_import_share" in result["failedCodes"]
    assert "browser_proof_not_audited_without_live_import_project" in result["failedCodes"]
