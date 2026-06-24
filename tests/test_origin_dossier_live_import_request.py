from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_dossier_live_import_request.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_dossier_live_import", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_artifact(root: Path, name: str, content: bytes | str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def write_receipt(
    root: Path,
    name: str,
    *,
    operation: str,
    provider: str,
    artifacts: list[Path],
    tokens: list[str] | None = None,
    external: bool = False,
) -> Path:
    delivered_links = list(tokens or [])
    if external:
        delivered_links.extend(
            [
                "operator_verified_live_run",
                f"provider_receipt_reference:{provider}:{operation}",
            ]
        )
    return write_json(
        root / name,
        {
            "operation": operation,
            "provider": provider,
            "status": "verified",
            "completedAtUtc": now_iso(),
            "artifactSha256": [sha256(artifact) for artifact in artifacts],
            "deliveredLinks": delivered_links,
        },
    )


def build_valid_fixture(tmp_path: Path) -> tuple[Path, dict[str, Path | str]]:
    root = tmp_path / "origin-live"
    project_id = "origin-live-gold"
    share_url = f"https://audio.chummer.run/share/{project_id}"
    source = write_artifact(root, "approved-source-packet.json", '{"externalProcessingConsent": true}\n')
    manuscript = write_artifact(
        root,
        "provider-manuscript.md",
        "Rain struck the clinic glass while the runner learned what a debt really costs.\n",
    )
    book = write_artifact(root, "book.pdf", b"%PDF-1.7\nreal provider finished book\n")
    cover = write_artifact(root, "story-scene-cover.png", b"\x89PNG\r\nselected face story scene render\n")
    audio = write_artifact(root, "audiobook.m4b", b"M4B real Unmixr narration bytes\n")
    video = write_artifact(root, "dossier-film.mp4", b"MP4 real dossier scene trailer bytes\n")

    source_receipt = write_receipt(
        root,
        "approved-source-packet.receipt.json",
        operation="origin_source_packet_approval",
        provider="Chummer",
        artifacts=[source],
        tokens=["approved_source_packet", "external_processing_consent"],
    )
    provider_receipt = write_receipt(
        root,
        "provider-manuscript.receipt.json",
        operation="provider_manuscript_import",
        provider="Inkfluence",
        artifacts=[manuscript],
        external=True,
    )
    humanizer_receipt = write_receipt(
        root,
        "undetectable-humanizer.receipt.json",
        operation="undetectable_humanizer_postprocess",
        provider="Undetectable Humanizer",
        artifacts=[manuscript],
        external=True,
    )
    canon_receipt = write_receipt(
        root,
        "chummer-canon-audit.receipt.json",
        operation="chummer_canon_audit",
        provider="Chummer",
        artifacts=[source, manuscript],
        tokens=["canon_audit_passed", "hard_conflicts:0", "privacy_findings:0"],
    )
    book_receipt = write_receipt(
        root,
        "book.receipt.json",
        operation="book_artifact_import",
        provider="Inkfluence",
        artifacts=[book],
        external=True,
    )
    cover_receipt = write_receipt(
        root,
        "story-scene-cover.receipt.json",
        operation="selected_face_scene_render",
        provider="scene-renderer",
        artifacts=[cover],
        tokens=[
            f"/account/work/origin-dossiers/{project_id}",
            f"/account/work/origin-dossiers/{project_id}/cover",
            "selected_character_face",
            "story_scene",
            f"provider_manuscript_sha256:{sha256(manuscript)}",
        ],
        external=True,
    )
    video_receipt = write_receipt(
        root,
        "dossier-film.receipt.json",
        operation="dossier_video_import",
        provider="video-renderer",
        artifacts=[video],
        external=True,
    )
    ea_job_receipt = write_json(
        root / "ea-audiobook-job.receipt.json",
        {
            "contract_name": "ea.telegram_epub_audiobook_job_receipt.v1",
            "status": "audiobookshelf_imported",
            "observed_at": now_iso(),
            "source": {
                "kind": "origin_dossier_story",
                "rights_basis": "operator_owned_private_origin_dossier",
            },
            "render": {
                "provider": "Unmixr",
                "audio_quality": {"status": "pass"},
            },
            "assembly": {
                "status": "m4b_ready",
                "output_file_ready": True,
                "output_file_sha256": sha256(audio),
                "chapter_metadata_embedded": True,
            },
            "audiobookshelf_import": {
                "status": "imported",
                "target_file_ready": True,
                "target_file_sha256": sha256(audio),
                "player_scoped_reference_status": "signed_reference_ready",
                "public_share_status": "public_share_ready",
                "public_share_url": share_url,
                "public_share_token_exposed": False,
                "public_share_raw_library_path_exposed": False,
                "public_share_telegram_delivery_status": "sent",
                "public_share_telegram_message_id_present": True,
                "public_share_telegram_callback_tokens_exposed": False,
                "public_share_telegram_audiobookshelf_token_exposed": False,
                "public_share_playback_e2e_status": "pass",
                "public_share_playback_e2e_track_response_status": 206,
                "public_share_playback_e2e_track_content_type": "audio/mp4",
                "public_share_playback_e2e_duration_seconds": 12.5,
                "public_share_playback_e2e_current_time_after_play_seconds": 2.0,
                "public_share_playback_e2e_media_error_present": False,
            },
            "privacy": {
                "raw_book_text_in_receipt": False,
                "telegram_chat_id_exposed": False,
                "telegram_message_id_exposed": False,
                "telegram_token_exposed": False,
                "provider_secret_exposed": False,
                "audiobookshelf_token_exposed": False,
                "audiobookshelf_raw_path_exposed": False,
                "private_job_path_exposed": False,
            },
        },
    )
    ea_live_receipt = write_json(
        root / "ea-telegram-live-delivery.receipt.json",
        {
            "contract_name": "ea.telegram_audiobook_live_delivery_receipt.v1",
            "status": "pass",
            "generated_at": now_iso(),
            "live_delivery_claim_allowed": True,
            "machine_playback_e2e_verified": True,
            "real_user_playback_acceptance_verified": False,
            "failed_codes": [],
            "selected_delivery": {
                "public_share_url_present": True,
                "public_share_host": "audio.chummer.run",
                "telegram_delivery_status": "sent",
                "telegram_delivery_message_id_present": True,
                "machine_playback_e2e_verified": True,
            },
            "privacy": {
                "raw_job_receipts_persisted": False,
                "public_share_urls_redacted_to_host": True,
                "telegram_message_ids_hashed": True,
                "provider_secret_exposed": False,
                "audiobookshelf_token_exposed": False,
            },
        },
    )
    manifest = {
        "projectId": project_id,
        "title": "A Gold Origin Dossier",
        "runnerAlias": "Kestrel",
        "audiobookshelfShareUrl": share_url,
        "sourcePacketPath": str(source),
        "sourcePacketReceiptPath": str(source_receipt),
        "providerManuscriptPath": str(manuscript),
        "providerManuscriptReceiptPath": str(provider_receipt),
        "humanizerReceiptPath": str(humanizer_receipt),
        "canonAuditReceiptPath": str(canon_receipt),
        "bookArtifactPath": str(book),
        "bookArtifactReceiptPath": str(book_receipt),
        "storySceneCoverPath": str(cover),
        "storySceneCoverReceiptPath": str(cover_receipt),
        "audiobookPath": str(audio),
        "dossierVideoPath": str(video),
        "dossierVideoReceiptPath": str(video_receipt),
        "eaAudiobookJobReceiptPath": str(ea_job_receipt),
        "eaTelegramLiveDeliveryReceiptPath": str(ea_live_receipt),
    }
    manifest_path = write_json(root / "live-manifest.json", manifest)
    paths: dict[str, Path | str] = {
        "root": root,
        "manifest": manifest_path,
        "eaJobReceipt": ea_job_receipt,
        "eaLiveReceipt": ea_live_receipt,
        "coverReceipt": cover_receipt,
        "shareUrl": share_url,
    }
    return manifest_path, paths


def test_materializes_chummer_import_request_from_live_origin_dossier_evidence(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    output = tmp_path / "out" / "request.json"

    result = module.materialize(manifest, output)

    assert result["status"] == "pass"
    assert result["goalCompletionClaimAllowed"] is False
    request = result["importRequest"]
    assert request["providerAuthoredManuscriptImported"] is True
    assert request["undetectableHumanizerApplied"] is True
    assert request["storySceneCoverUsesSelectedCharacterFace"] is True
    assert request["audiobookshelfPlaybackVerified"] is True
    assert request["telegramShareDelivered"] is True
    assert request["missingGoldRequirements"] == []
    assert Path(request["audiobookshelfImportReceiptPath"]).is_file()
    assert Path(request["telegramShareDeliveryReceiptPath"]).is_file()


def test_rejects_untrusted_audiobookshelf_share_url(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["audiobookshelfShareUrl"] = "https://evil.example/share/origin-live-gold"
    write_json(manifest, payload)

    with pytest.raises(module.ValidationError, match="trusted chummer.run Audiobookshelf"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_ea_delivery_without_public_share(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["eaLiveReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["selected_delivery"]["public_share_url_present"] = False
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="public share URL"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_raw_audiobookshelf_path_or_secret_leak(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["eaJobReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["audiobookshelf_import"]["leaked_raw_path"] = "/docker/EA/data/audiobooks/jobs/private/job.json"
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="raw secret/path"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_non_approved_audiobook_provider(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["eaJobReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["render"]["provider"] = "edge_tts"
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="Inkfluence or Unmixr"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_fallback_or_placeholder_receipt_markers(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["eaLiveReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["note"] = "fallback narration path"
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="fake/fallback"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_cover_not_bound_to_story_scene(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["coverReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["deliveredLinks"] = [
        item
        for item in receipt["deliveredLinks"]
        if "story_scene" not in item and "provider_manuscript_sha256" not in item
    ]
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="actual story scene"):
        module.materialize(manifest, tmp_path / "out.json")
