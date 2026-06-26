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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
    audiobook_share_url = f"https://audio.chummer.run/share/{project_id}-audiobook"
    dossier_share_url = f"https://audio.chummer.run/share/{project_id}-dossier"
    source = write_artifact(root, "approved-source-packet.json", '{"externalProcessingConsent": true}\n')
    manuscript = write_artifact(
        root,
        "provider-manuscript.md",
        "Rain struck the clinic glass while the runner learned what a debt really costs.\n",
    )
    book = write_artifact(root, "book.pdf", b"%PDF-1.7\nreal provider finished book\n")
    ebook = write_artifact(root, "ebook.epub", b"PK\x03\x04real provider finished ebook\n")
    cover = write_artifact(root, "story-scene-cover.png", b"\x89PNG\r\nselected face story scene render\n")
    audio = write_artifact(root, "audiobook.m4b", b"M4B real Unmixr narration bytes\n")
    video = write_artifact(root, "dossier-film.mp4", b"MP4 real dossier scene trailer bytes\n")
    movie_poster = write_artifact(root, "movie-poster.jpg", cover.read_bytes())

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
    humanizer_quality_receipt = write_json(
        root / "undetectable-humanizer-quality.receipt.json",
        {
            "contractName": "chummer.origin_dossier.humanizer_quality_gate.v1",
            "provider": "Undetectable Humanizer",
            "operation": "humanizer_quality_gate",
            "status": "pass",
            "goldEligible": True,
            "issues": [],
            "sourceTextSha256": sha256(manuscript),
            "candidateTextSha256": sha256(manuscript),
            "rawCredentialExposed": False,
            "rawProviderTokenExposed": False,
            "createdAtUtc": now_iso(),
            "metrics": {
                "sourceContentOverlapRatio": 0.88,
                "fusedArtifactCount": 0,
                "providerPreambleCount": 0,
            },
        },
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
    ebook_dossier_receipt = write_receipt(
        root,
        "ebook-audiobookshelf-dossier.receipt.json",
        operation="audiobookshelf_dossier_import",
        provider="Audiobookshelf",
        artifacts=[ebook],
        tokens=[dossier_share_url],
        external=True,
    )
    ebook_dossier_payload = json.loads(ebook_dossier_receipt.read_text(encoding="utf-8"))
    ebook_dossier_payload["audiobookshelfDossierShareUrl"] = dossier_share_url
    write_json(ebook_dossier_receipt, ebook_dossier_payload)
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
                "public_share_url": audiobook_share_url,
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
    ea_m4b_provider_receipt = write_json(
        root / "ea-m4b-provider-import.receipt.json",
        {
            "contractName": "ea.origin_m4b_provider_import_gate.v1",
            "operation": "origin_m4b_provider_import_gate",
            "provider": "EA",
            "status": "pass",
            "goldEligible": True,
            "createdAtUtc": now_iso(),
            "namespace": "origin.chummer.run/Varga/Mira/Kestrel",
            "m4bPath": "origin.chummer.run/Varga/Mira/Kestrel/audiobook/audiobook.m4b",
            "m4bSha256": sha256(audio),
            "coverPath": "origin.chummer.run/Varga/Mira/Kestrel/audiobook/cover.jpg",
            "coverSha256": sha256(cover),
            "sourceSha256": sha256(manuscript),
            "providerReceiptPath": "origin.chummer.run/Varga/Mira/Kestrel/audiobook/provider-m4b.receipt.json",
            "coverReceiptPath": "origin.chummer.run/Varga/Mira/Kestrel/audiobook/m4b-cover.receipt.json",
            "issues": [],
            "shareCreated": False,
            "rawRuntimePathsExposed": False,
            "rawCredentialExposed": False,
            "rawProviderTokenExposed": False,
            "tokens": [
                "origin.chummer.run/Varga/Mira/Kestrel",
                sha256(audio),
                sha256(cover),
                sha256(manuscript),
                "provider_m4b_verified",
                "m4b_cover_embedded",
            ],
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
                "origin_edition_link_bundle": {
                    "status": "sent",
                    "project_id": project_id,
                    "origin_namespace_sha256": sha256_text("origin.chummer.run/Varga/Mira/Kestrel"),
                    "telegram_delivery_status": "sent",
                    "telegram_message_id_present": True,
                    "all_required_links_present": True,
                    "raw_urls_exposed": False,
                    "read_url_sha256": sha256_text(f"https://chummer.run/account/work/origin-dossiers/{project_id}/read"),
                    "listen_url_sha256": sha256_text(f"https://chummer.run/account/work/origin-dossiers/{project_id}/listen"),
                    "watch_url_sha256": sha256_text(f"https://chummer.run/account/work/origin-dossiers/{project_id}/video"),
                    "open_in_chummer_url_sha256": sha256_text(f"https://chummer.run/account/work/origin-dossiers/{project_id}"),
                },
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
    final_bundle_receipt = write_json(
        root / "final-origin-edition-bundle.receipt.json",
        {
            "contractName": "chummer.origin_edition.final_no_fallback_bundle_audit.v1",
            "operation": "origin_edition_final_no_fallback_bundle_audit",
            "provider": "Chummer",
            "status": "pass",
            "goldEligible": True,
            "completedAtUtc": now_iso(),
            "namespace": "origin.chummer.run/Varga/Mira/Kestrel",
            "blockedSurfaces": [],
            "surfaces": [
                {"name": "approved_canon_packet", "status": "pass"},
                {"name": "provider_manuscript", "status": "pass"},
                {"name": "humanizer_receipt", "status": "pass"},
                {"name": "humanizer_quality_receipt", "status": "pass"},
                {"name": "cover", "status": "pass"},
                {"name": "ebook", "status": "pass"},
                {"name": "pdf", "status": "pass"},
                {"name": "pdf_cover_receipt", "status": "pass"},
                {"name": "dossier_audiobookshelf_receipt", "status": "pass"},
                {"name": "m4b_provider_gate", "status": "pass"},
                {"name": "cover_consistency", "status": "pass"},
                {"name": "movie", "status": "pass"},
                {"name": "movie_receipt", "status": "pass"},
                {"name": "real_m4b_artifact", "status": "pass"},
                {"name": "audiobookshelf_audiobook_receipt", "status": "pass"},
            ],
        },
    )
    manifest = {
        "projectId": project_id,
        "title": "A Gold Origin Dossier",
        "runnerAlias": "Kestrel",
        "familyName": "Varga",
        "givenName": "Mira",
        "runnerName": "Kestrel",
        "originEditionNamespace": "origin.chummer.run/Varga/Mira/Kestrel",
        "baseUrl": "https://chummer.run",
        "audiobookshelfShareUrl": audiobook_share_url,
        "audiobookshelfDossierShareUrl": dossier_share_url,
        "audiobookshelfAudiobookShareUrl": audiobook_share_url,
        "sourcePacketPath": str(source),
        "sourcePacketReceiptPath": str(source_receipt),
        "providerManuscriptPath": str(manuscript),
        "providerManuscriptReceiptPath": str(provider_receipt),
        "humanizerReceiptPath": str(humanizer_receipt),
        "humanizerQualityReceiptPath": str(humanizer_quality_receipt),
        "canonAuditReceiptPath": str(canon_receipt),
        "bookArtifactPath": str(book),
        "bookArtifactReceiptPath": str(book_receipt),
        "ebookArtifactPath": str(ebook),
        "ebookAudiobookshelfImportReceiptPath": str(ebook_dossier_receipt),
        "storySceneCoverPath": str(cover),
        "storySceneCoverReceiptPath": str(cover_receipt),
        "audiobookPath": str(audio),
        "dossierVideoPath": str(video),
        "moviePosterPath": str(movie_poster),
        "dossierVideoReceiptPath": str(video_receipt),
        "eaAudiobookJobReceiptPath": str(ea_job_receipt),
        "eaM4bProviderImportReceiptPath": str(ea_m4b_provider_receipt),
        "eaTelegramLiveDeliveryReceiptPath": str(ea_live_receipt),
        "finalNoFallbackNoSentinelAuditReceiptPath": str(final_bundle_receipt),
    }
    manifest_path = write_json(root / "live-manifest.json", manifest)
    paths: dict[str, Path | str] = {
        "root": root,
        "manifest": manifest_path,
        "eaJobReceipt": ea_job_receipt,
        "eaM4bProviderReceipt": ea_m4b_provider_receipt,
        "eaLiveReceipt": ea_live_receipt,
        "finalBundleReceipt": final_bundle_receipt,
        "coverReceipt": cover_receipt,
        "ebookDossierReceipt": ebook_dossier_receipt,
        "humanizerQualityReceipt": humanizer_quality_receipt,
        "audiobookShareUrl": audiobook_share_url,
        "dossierShareUrl": dossier_share_url,
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
    assert Path(request["humanizerQualityReceiptPath"]).is_file()
    assert request["storySceneCoverUsesSelectedCharacterFace"] is True
    assert Path(request["moviePosterPath"]).is_file()
    assert Path(request["dossierVideoPosterPath"]).is_file()
    assert result["evidence"]["moviePosterSha256"] == result["evidence"]["storySceneCoverSha256"]
    assert request["audiobookshelfPlaybackVerified"] is True
    assert request["telegramShareDelivered"] is True
    assert request["familyName"] == "Varga"
    assert request["givenName"] == "Mira"
    assert request["runnerName"] == "Kestrel"
    assert request["originEditionNamespace"] == "origin.chummer.run/Varga/Mira/Kestrel"
    assert request["audiobookshelfDossierShareUrl"] == "https://audio.chummer.run/share/origin-live-gold-dossier"
    assert request["audiobookshelfAudiobookShareUrl"] == "https://audio.chummer.run/share/origin-live-gold-audiobook"
    assert request["missingGoldRequirements"] == []
    assert result["evidence"]["humanizerQualityReceiptSha256"] == sha256(Path(request["humanizerQualityReceiptPath"]))
    assert Path(request["ebookArtifactPath"]).is_file()
    assert Path(request["ebookAudiobookshelfImportReceiptPath"]).is_file()
    assert result["evidence"]["ebookArtifactSha256"] == sha256(Path(request["ebookArtifactPath"]))
    assert result["evidence"]["ebookAudiobookshelfImportReceiptSha256"] == sha256(Path(request["ebookAudiobookshelfImportReceiptPath"]))
    assert Path(request["m4bProviderImportReceiptPath"]).is_file()
    assert Path(request["audiobookshelfImportReceiptPath"]).is_file()
    assert Path(request["telegramShareDeliveryReceiptPath"]).is_file()
    assert Path(request["finalNoFallbackNoSentinelAuditReceiptPath"]).is_file()
    assert "/origin.chummer.run/Varga/Mira/Kestrel/audiobook/" in request["audiobookshelfImportReceiptPath"].replace("\\", "/")
    assert "/origin.chummer.run/Varga/Mira/Kestrel/audiobook/" in request["telegramShareDeliveryReceiptPath"].replace("\\", "/")
    assert result["evidence"]["eaM4bProviderImportReceiptSha256"] == sha256(Path(request["m4bProviderImportReceiptPath"]))
    telegram_receipt = json.loads(Path(request["telegramShareDeliveryReceiptPath"]).read_text(encoding="utf-8"))
    assert "/account/work/origin-dossiers/origin-live-gold/video" in telegram_receipt["deliveredLinks"]
    assert "/account/work/origin-dossiers/origin-live-gold/watch" not in telegram_receipt["deliveredLinks"]
    assert telegram_receipt["linkBundleSha256"]["open_in_chummer"] == sha256_text("/account/work/origin-dossiers/origin-live-gold")
    assert telegram_receipt["linkBundleSha256"]["read"] == sha256_text("/account/work/origin-dossiers/origin-live-gold/read")
    assert telegram_receipt["linkBundleSha256"]["listen"] == sha256_text("/account/work/origin-dossiers/origin-live-gold/listen")
    assert telegram_receipt["linkBundleSha256"]["watch"] == sha256_text("/account/work/origin-dossiers/origin-live-gold/video")
    assert sha256_text("/account/work/origin-dossiers/origin-live-gold/watch") not in telegram_receipt["deliveredLinks"]


def test_rejects_missing_ebook_dossier_import_receipt(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload.pop("ebookAudiobookshelfImportReceiptPath", None)
    write_json(manifest, payload)

    with pytest.raises(module.ValidationError, match="ebookAudiobookshelfImportReceiptPath"):
        module.materialize(manifest, tmp_path / "out.json")


def test_uses_book_artifact_as_legacy_ebook_artifact_when_ebook_path_is_absent(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    ebook_path = payload["ebookArtifactPath"]
    legacy_book_receipt = write_receipt(
        tmp_path / "origin-live",
        "legacy-ebook-as-book.receipt.json",
        operation="book_artifact_import",
        provider="Inkfluence",
        artifacts=[Path(ebook_path)],
        external=True,
    )
    payload["bookArtifactPath"] = ebook_path
    payload["bookArtifactReceiptPath"] = str(legacy_book_receipt)
    payload.pop("ebookArtifactPath", None)
    write_json(manifest, payload)

    result = module.materialize(manifest, tmp_path / "out.json")

    request = result["importRequest"]
    assert request["ebookArtifactPath"] == request["bookArtifactPath"]
    assert result["evidence"]["ebookArtifactSha256"] == result["evidence"]["bookArtifactSha256"]


def test_uses_default_movie_poster_path_when_manifest_omits_poster_path(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    namespace = payload["originEditionNamespace"]
    cover_path = Path(payload["storySceneCoverPath"])
    default_poster = Path(payload["sourcePacketPath"]).parent / namespace / "movie" / "poster.jpg"
    default_poster.parent.mkdir(parents=True, exist_ok=True)
    default_poster.write_bytes(cover_path.read_bytes())
    payload.pop("moviePosterPath", None)
    payload.pop("dossierVideoPosterPath", None)
    write_json(manifest, payload)

    result = module.materialize(manifest, tmp_path / "out.json")

    request = result["importRequest"]
    assert request["moviePosterPath"] == str(default_poster)
    assert request["dossierVideoPosterPath"] == str(default_poster)
    assert result["evidence"]["moviePosterSha256"] == result["evidence"]["storySceneCoverSha256"]


def test_rejects_movie_poster_that_does_not_match_story_scene_cover(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    poster = Path(payload["moviePosterPath"])
    poster.write_bytes(b"different poster bytes")
    write_json(manifest, payload)

    with pytest.raises(module.ValidationError, match="movie poster must match"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_missing_chummer_base_url(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload.pop("baseUrl", None)
    payload.pop("chummerBaseUrl", None)
    payload.pop("originEditionBaseUrl", None)
    write_json(manifest, payload)

    with pytest.raises(module.ValidationError, match="baseUrl"):
        module.materialize(manifest, tmp_path / "out.json")


def test_accepts_explicit_base_url_override_when_manifest_omits_base_url(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload.pop("baseUrl", None)
    payload.pop("chummerBaseUrl", None)
    payload.pop("originEditionBaseUrl", None)
    write_json(manifest, payload)

    result = module.materialize(
        manifest,
        tmp_path / "out.json",
        base_url_override="https://chummer.run",
    )

    request = result["importRequest"]
    assert request["baseUrl"] == "https://chummer.run"
    assert request["bookArtifactUrl"] == "https://chummer.run/account/work/origin-dossiers/origin-live-gold/book"
    assert request["dossierVideoUrl"] == "https://chummer.run/account/work/origin-dossiers/origin-live-gold/video"
    assert request["storySceneCoverUrl"] == "https://chummer.run/account/work/origin-dossiers/origin-live-gold/cover"


def test_rejects_ebook_dossier_import_share_mismatch(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["ebookDossierReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["audiobookshelfDossierShareUrl"] = "https://audio.chummer.run/share/wrong-dossier"
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="dossier share URL does not match manifest"):
        module.materialize(manifest, tmp_path / "out.json")


def test_materializes_import_request_with_internal_chummer_originbookengine_manuscript(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    provider_receipt = Path(paths["root"]) / "provider-manuscript.chummer.receipt.json"
    write_json(
        provider_receipt,
        {
            "operation": "provider_manuscript_import",
            "provider": "Chummer OriginBookEngine",
            "status": "verified",
            "completedAtUtc": now_iso(),
            "artifactSha256": [sha256(Path(payload["providerManuscriptPath"]))],
            "tokens": [
                "approved_runner_canon_only",
                "no_provider_created_facts_entered_canon",
                "internal_standard_origin_dossier_generation",
            ],
        },
    )
    payload["providerManuscriptReceiptPath"] = str(provider_receipt)
    write_json(manifest, payload)

    result = module.materialize(manifest, tmp_path / "out.json")

    assert result["status"] == "pass"
    assert result["importRequest"]["providerAuthoredManuscriptImported"] is True


def test_materializes_import_request_with_custom_origin_context_and_base_url(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    project_id = "case-ari-ghost"
    namespace = "origin.chummer.run/Case/Ari/Ghost"
    base_url = "https://staging.chummer.run"
    payload.update(
        {
            "projectId": project_id,
            "familyName": "Case",
            "givenName": "Ari",
            "runnerName": "Ghost",
            "runnerAlias": "Ghost",
            "originEditionNamespace": namespace,
            "baseUrl": base_url,
        }
    )
    write_json(manifest, payload)
    m4b_receipt_path = Path(paths["eaM4bProviderReceipt"])
    m4b_receipt = json.loads(m4b_receipt_path.read_text(encoding="utf-8"))
    m4b_receipt["namespace"] = namespace
    m4b_receipt["tokens"] = [
        namespace if token == "origin.chummer.run/Varga/Mira/Kestrel" else token
        for token in m4b_receipt["tokens"]
    ]
    write_json(m4b_receipt_path, m4b_receipt)
    cover_receipt_path = Path(paths["coverReceipt"])
    cover_receipt = json.loads(cover_receipt_path.read_text(encoding="utf-8"))
    cover_receipt["deliveredLinks"] = [
        f"/account/work/origin-dossiers/{project_id}" if token == "/account/work/origin-dossiers/origin-live-gold" else token
        for token in cover_receipt["deliveredLinks"]
    ]
    cover_receipt["deliveredLinks"] = [
        f"/account/work/origin-dossiers/{project_id}/cover" if token == "/account/work/origin-dossiers/origin-live-gold/cover" else token
        for token in cover_receipt["deliveredLinks"]
    ]
    write_json(cover_receipt_path, cover_receipt)
    live_receipt_path = Path(paths["eaLiveReceipt"])
    live_receipt = json.loads(live_receipt_path.read_text(encoding="utf-8"))
    bundle = live_receipt["selected_delivery"]["origin_edition_link_bundle"]
    bundle["project_id"] = project_id
    bundle["origin_namespace_sha256"] = sha256_text(namespace)
    bundle["read_url_sha256"] = sha256_text(f"{base_url}/account/work/origin-dossiers/{project_id}/read")
    bundle["listen_url_sha256"] = sha256_text(f"{base_url}/account/work/origin-dossiers/{project_id}/listen")
    bundle["watch_url_sha256"] = sha256_text(f"{base_url}/account/work/origin-dossiers/{project_id}/video")
    bundle["open_in_chummer_url_sha256"] = sha256_text(f"{base_url}/account/work/origin-dossiers/{project_id}")
    write_json(live_receipt_path, live_receipt)

    result = module.materialize(manifest, tmp_path / "out.json")
    request = result["importRequest"]

    assert result["status"] == "pass"
    assert result["chummerRunOwnerUrl"] == f"{base_url}/account/work/origin-dossiers/{project_id}"
    assert request["originEditionNamespace"] == namespace
    assert request["bookArtifactUrl"] == f"{base_url}/account/work/origin-dossiers/{project_id}/book"
    assert request["dossierVideoUrl"] == f"{base_url}/account/work/origin-dossiers/{project_id}/video"
    assert request["storySceneCoverUrl"] == f"{base_url}/account/work/origin-dossiers/{project_id}/cover"
    assert f"/{namespace}/audiobook/" in request["audiobookshelfImportReceiptPath"].replace("\\", "/")


def test_rejects_untrusted_audiobookshelf_share_url(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["audiobookshelfAudiobookShareUrl"] = "https://evil.example/share/origin-live-gold"
    write_json(manifest, payload)

    with pytest.raises(module.ValidationError, match="audiobookshelfAudiobookShareUrl"):
        module.materialize(manifest, tmp_path / "out.json")


def test_accepts_live_audiobookshelf_host_for_dossier_and_audiobook_shares(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    live_audiobook_share_url = "https://audiobookshelf.girschele.com/audiobookshelf/share/origin-live-gold-audiobook"
    live_dossier_share_url = "https://audiobookshelf.girschele.com/audiobookshelf/share/origin-live-gold-dossier"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["audiobookshelfShareUrl"] = live_audiobook_share_url
    payload["audiobookshelfDossierShareUrl"] = live_dossier_share_url
    payload["audiobookshelfAudiobookShareUrl"] = payload["audiobookshelfShareUrl"]
    write_json(manifest, payload)
    ea_job_receipt = json.loads(Path(paths["eaJobReceipt"]).read_text(encoding="utf-8"))
    ea_job_receipt["audiobookshelf_import"]["public_share_url"] = live_audiobook_share_url
    write_json(Path(paths["eaJobReceipt"]), ea_job_receipt)
    ea_live_receipt = json.loads(Path(paths["eaLiveReceipt"]).read_text(encoding="utf-8"))
    ea_live_receipt["selected_delivery"]["public_share_host"] = "audiobookshelf.girschele.com"
    write_json(Path(paths["eaLiveReceipt"]), ea_live_receipt)
    ebook_dossier_receipt = json.loads(Path(paths["ebookDossierReceipt"]).read_text(encoding="utf-8"))
    ebook_dossier_receipt["audiobookshelfDossierShareUrl"] = live_dossier_share_url
    ebook_dossier_receipt["deliveredLinks"] = [
        live_dossier_share_url if token == str(paths["dossierShareUrl"]) else token
        for token in ebook_dossier_receipt["deliveredLinks"]
    ]
    write_json(Path(paths["ebookDossierReceipt"]), ebook_dossier_receipt)

    result = module.materialize(manifest, tmp_path / "out.json")

    assert result["status"] == "pass"
    request = result["importRequest"]
    assert request["audiobookshelfDossierShareUrl"] == live_dossier_share_url
    assert request["audiobookshelfAudiobookShareUrl"] == live_audiobook_share_url


def test_rejects_missing_dossier_share_url(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["audiobookshelfDossierShareUrl"] = ""
    write_json(manifest, payload)

    with pytest.raises(module.ValidationError, match="audiobookshelfDossierShareUrl"):
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


def test_rejects_missing_m4b_provider_import_gate(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload.pop("eaM4bProviderImportReceiptPath", None)
    write_json(manifest, payload)

    with pytest.raises(module.ValidationError, match="eaM4bProviderImportReceiptPath"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_failed_m4b_provider_import_gate(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["eaM4bProviderReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["status"] = "blocked"
    receipt["goldEligible"] = False
    receipt["issues"] = ["m4b_missing"]
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="M4B provider import gate is not pass"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_m4b_provider_import_gate_hash_mismatch(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["eaM4bProviderReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["sourceSha256"] = "0" * 64
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="manuscript/source hash mismatch"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_ea_delivery_without_origin_edition_link_bundle(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["eaLiveReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["selected_delivery"].pop("origin_edition_link_bundle", None)
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="Origin Edition link bundle"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_ea_delivery_with_origin_edition_link_hash_mismatch(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["eaLiveReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["selected_delivery"]["origin_edition_link_bundle"]["watch_url_sha256"] = "0" * 64
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="watch_url_sha256"):
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

    with pytest.raises(module.ValidationError, match="premium audio provider registry"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_disguised_audiobook_provider_substring(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["eaJobReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["render"]["provider"] = "NotUnmixr Account 02"
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="premium audio provider registry"):
        module.materialize(manifest, tmp_path / "out.json")


def test_accepts_configured_audiobook_provider_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHUMMER_ORIGIN_AUDIO_PROVIDER_TOKENS", "premiumvoice")
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["eaJobReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["render"]["provider"] = "PremiumVoice Account 04"
    write_json(receipt_path, receipt)

    result = module.materialize(manifest, tmp_path / "out.json")

    assert result["status"] == "pass"
    assert result["audiobookProvider"] == "PremiumVoice Account 04"


def test_accepts_configured_manuscript_provider_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHUMMER_ORIGIN_MANUSCRIPT_PROVIDER_TOKENS", "guided memoir lane")
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    receipt_path = Path(payload["providerManuscriptReceiptPath"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["provider"] = "Guided Memoir Lane 02"
    receipt["deliveredLinks"] = [
        token.replace("Inkfluence", "Guided Memoir Lane 02")
        for token in receipt.get("deliveredLinks", [])
    ]
    write_json(receipt_path, receipt)

    result = module.materialize(manifest, tmp_path / "out.json")

    assert result["status"] == "pass"


def test_rejects_disguised_manuscript_provider_substring(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    receipt_path = Path(payload["providerManuscriptReceiptPath"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["provider"] = "FakeInkfluenceProxy"
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="manuscript provider registry"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_failed_undetectable_humanizer_quality_gate(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    receipt_path = Path(payload["humanizerReceiptPath"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["status"] = "failed_quality_gate"
    receipt["goldEligible"] = False
    receipt["qualityIssues"] = [
        {
            "issue": "spacing_or_preamble_artifacts",
            "markers": ["Pleaseprovidetheinputtexttoberewritten"],
        }
    ]
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="receipt status is not verified"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_missing_humanizer_quality_gate(tmp_path: Path) -> None:
    module = load_module()
    manifest, _paths = build_valid_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload.pop("humanizerQualityReceiptPath", None)
    write_json(manifest, payload)

    with pytest.raises(module.ValidationError, match="humanizerQualityReceiptPath"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_failed_deterministic_humanizer_quality_gate(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["humanizerQualityReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["status"] = "failed_quality_gate"
    receipt["goldEligible"] = False
    receipt["issues"] = ["fused_spacing_artifacts_detected"]
    receipt["metrics"]["fusedArtifactCount"] = 12
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="humanizer quality gate is not pass"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_humanizer_quality_gate_source_hash_mismatch(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["humanizerQualityReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["sourceTextSha256"] = "0" * 64
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="source manuscript hash mismatch"):
        module.materialize(manifest, tmp_path / "out.json")


def test_rejects_audiobook_import_when_provider_text_fidelity_gate_failed(tmp_path: Path) -> None:
    module = load_module()
    manifest, paths = build_valid_fixture(tmp_path)
    receipt_path = Path(paths["eaJobReceipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["audiobookshelf_import"]["public_share_status"] = "blocked_audio_publication_gate"
    receipt["audiobookshelf_import"]["public_share_url"] = ""
    receipt["audiobookshelf_import"]["public_share_playback_e2e_status"] = "blocked"
    receipt["render"]["audio_quality"] = {
        "status": "fail",
        "issues": ["stt_transcript_not_book_text"],
    }
    write_json(receipt_path, receipt)

    with pytest.raises(module.ValidationError, match="public share is not ready"):
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
