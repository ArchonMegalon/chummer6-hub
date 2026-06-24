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
            "listen_url": f"{base_url}/account/work/origin-dossiers/{project_id}/listen",
            "audiobookshelf_redirect": share_url,
            "logged_in_browser_verified": True,
            "selected_face_cover_visible": True,
            "chummer_run_listen_gate_verified": True,
            "owner_playback_e2e_verified": live,
        },
    )


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


def test_gold_e2e_audit_blocks_untrusted_browser_playback_redirect(tmp_path: Path) -> None:
    audit_module = load_module(AUDIT_SCRIPT, "origin_dossier_gold_audit_untrusted")
    live_import, paths = build_live_import_request(tmp_path)
    browser_proof = write_browser_proof(
        tmp_path,
        project_id="origin-live-gold",
        share_url="https://audiobookshelf.girschele.com/share/origin-live-gold",
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
