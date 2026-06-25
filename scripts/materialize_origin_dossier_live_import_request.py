#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_context import OriginEditionContext
from origin_edition_provider_config import is_trusted_audiobookshelf_share, origin_owner_url


CONTRACT_NAME = "chummer.origin_dossier_live_artifact_import_request.v1"
EA_JOB_RECEIPT_CONTRACT_NAME = "ea.telegram_epub_audiobook_job_receipt.v1"
EA_LIVE_DELIVERY_CONTRACT_NAME = "ea.telegram_audiobook_live_delivery_receipt.v1"
EA_M4B_PROVIDER_IMPORT_CONTRACT_NAME = "ea.origin_m4b_provider_import_gate.v1"
HUMANIZER_QUALITY_CONTRACT_NAME = "chummer.origin_dossier.humanizer_quality_gate.v1"
DEFAULT_OUTPUT_NAME = "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
APPROVED_MANUSCRIPT_PROVIDERS = ("inkfluence", "youbooks", "first book", "firstbook", "chummer originbookengine")
APPROVED_AUDIO_PROVIDERS = ("inkfluence", "unmixr")
FAKE_MARKERS = (
    "stub",
    "fallback",
    "placeholder",
    "self_generated",
    "self-generated",
    "local_fixture",
    "browser proof",
)
RAW_EVIDENCE_LEAK_MARKERS = (
    "EA_AUDIOBOOKSHELF_API_TOKEN",
    "EA_TELEGRAM_BOT_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "UNMIXR_API_KEY",
    "api.telegram.org/bot",
    "audiobookshelf_api_token",
    "telegram_bot_token",
    "provider_voice_id",
    "raw_voice_id",
    "data/audiobooks/jobs",
    "data/audiobooks/audiobookshelf",
    "/docker/EA/data/audiobooks",
)
VERIFIED_STATUSES = ("verified", "delivered", "ok", "success")
LIVE_TOKEN = "operator_verified_live_run"
PROVIDER_REFERENCE_TOKEN = "provider_receipt_reference"


class ValidationError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surfaced as operator validation detail
        raise ValidationError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValidationError(f"{path}: expected JSON object")
    return parsed


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ValidationError(f"{path}: cannot hash artifact: {exc}") from exc
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_file(value: object, field: str) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"{field}: path is required")
    if _contains_fake_marker(text):
        raise ValidationError(f"{field}: fake/fallback marker is not allowed")
    path = Path(text).expanduser()
    if not path.is_file():
        raise ValidationError(f"{field}: file does not exist: {path}")
    if path.stat().st_size <= 0:
        raise ValidationError(f"{field}: file is empty: {path}")
    return path


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _contains_fake_marker(value: object) -> bool:
    if isinstance(value, str):
        lowered = (
            value.lower()
            .replace("no-fallback", "")
            .replace("no_fallback", "")
            .replace("nofallback", "")
            .replace("no fallback", "")
        )
        return any(marker in lowered for marker in FAKE_MARKERS)
    if isinstance(value, dict):
        return any(_contains_fake_marker(key) or _contains_fake_marker(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_fake_marker(item) for item in value)
    return False


def _reject_fake_markers(value: object, label: str) -> None:
    if _contains_fake_marker(value):
        raise ValidationError(f"{label}: fake/fallback marker is not allowed")


def _reject_raw_evidence_leaks(value: object, label: str) -> None:
    text = _json_text(value)
    for marker in RAW_EVIDENCE_LEAK_MARKERS:
        if marker in text:
            raise ValidationError(f"{label}: raw secret/path/provider evidence leak detected: {marker}")
    if '"voice_id"' in text or "'voice_id'" in text:
        raise ValidationError(f"{label}: raw provider voice_id leak detected")


def _contains_token(value: object, token: str) -> bool:
    if not token:
        return True
    if isinstance(value, str):
        return token.lower() in value.lower()
    if isinstance(value, dict):
        return any(token.lower() in str(key).lower() or _contains_token(item, token) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_token(item, token) for item in value)
    return False


def _string(value: object) -> str:
    return str(value or "").strip()


def _bool(value: object) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes", "pass", "ready", "verified"}


def _parse_time(value: object) -> bool:
    text = _string(value)
    if not text:
        return False
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _completion_time_present(receipt: dict[str, Any]) -> bool:
    fields = (
        "completedAtUtc",
        "completed_at_utc",
        "deliveredAtUtc",
        "delivered_at_utc",
        "createdAtUtc",
        "created_at_utc",
        "observed_at",
        "generated_at",
    )
    return any(_parse_time(receipt.get(field)) for field in fields)


def _trusted_audiobookshelf_share_url(url: str) -> bool:
    return is_trusted_audiobookshelf_share(url)


def _owner_path(project_id: str, artifact_kind: str | None = None) -> str:
    base = f"/account/work/origin-dossiers/{project_id}"
    return f"{base}/{artifact_kind}" if artifact_kind else base


def _provider_allowed(provider: str, allowed: tuple[str, ...]) -> bool:
    lowered = provider.lower()
    return any(token in lowered for token in allowed)


def _validate_receipt(
    *,
    path: Path,
    label: str,
    operation: str,
    provider_token: str | None,
    artifact_hashes: tuple[str, ...] = (),
    required_tokens: tuple[str, ...] = (),
    external: bool = False,
) -> dict[str, Any]:
    receipt = _read_json(path)
    _reject_fake_markers(receipt, label)
    _reject_raw_evidence_leaks(receipt, label)
    if _string(receipt.get("operation")).lower() != operation.lower():
        raise ValidationError(f"{label}: expected operation={operation}")
    if provider_token and provider_token.lower() not in _string(receipt.get("provider")).lower():
        raise ValidationError(f"{label}: expected provider token={provider_token}")
    status = _string(receipt.get("status")).lower()
    if status and status not in VERIFIED_STATUSES:
        raise ValidationError(f"{label}: receipt status is not verified/delivered")
    if not _completion_time_present(receipt):
        raise ValidationError(f"{label}: completion timestamp is required")
    for artifact_hash in artifact_hashes:
        if not _contains_token(receipt, artifact_hash):
            raise ValidationError(f"{label}: missing artifact hash {artifact_hash}")
    tokens = list(required_tokens)
    if external:
        tokens.extend((LIVE_TOKEN, PROVIDER_REFERENCE_TOKEN))
    for token in tokens:
        if not _contains_token(receipt, token):
            raise ValidationError(f"{label}: missing required token {token}")
    return receipt


def _validate_provider_manuscript_receipt(path: Path, manuscript_hash: str) -> None:
    raw = _read_json(path)
    provider = _json_text(raw)
    internal_chummer_origin = _provider_allowed(provider, ("chummer originbookengine",))
    receipt = _validate_receipt(
        path=path,
        label="providerManuscriptReceiptPath",
        operation="provider_manuscript_import",
        provider_token=None,
        artifact_hashes=(manuscript_hash,),
        external=not internal_chummer_origin,
    )
    if not _provider_allowed(_json_text(receipt), APPROVED_MANUSCRIPT_PROVIDERS):
        raise ValidationError("providerManuscriptReceiptPath: provider must be Inkfluence, Youbooks, First Book, or Chummer OriginBookEngine")


def _validate_humanizer_quality_receipt(path: Path, manuscript_hash: str) -> None:
    receipt = _read_json(path)
    _reject_fake_markers(receipt, "humanizerQualityReceiptPath")
    _reject_raw_evidence_leaks(receipt, "humanizerQualityReceiptPath")
    if _string(receipt.get("contractName")) != HUMANIZER_QUALITY_CONTRACT_NAME:
        raise ValidationError("humanizerQualityReceiptPath: unsupported contract")
    if _string(receipt.get("operation")) != "humanizer_quality_gate":
        raise ValidationError("humanizerQualityReceiptPath: expected operation=humanizer_quality_gate")
    if "Undetectable" not in _string(receipt.get("provider")):
        raise ValidationError("humanizerQualityReceiptPath: provider must be Undetectable Humanizer")
    if _string(receipt.get("status")) != "pass":
        raise ValidationError("humanizerQualityReceiptPath: humanizer quality gate is not pass")
    if receipt.get("goldEligible") is not True:
        raise ValidationError("humanizerQualityReceiptPath: humanizer quality gate is not gold eligible")
    if receipt.get("issues") not in ([], None):
        raise ValidationError("humanizerQualityReceiptPath: humanizer quality gate has issues")
    if _string(receipt.get("sourceTextSha256")) != manuscript_hash:
        raise ValidationError("humanizerQualityReceiptPath: source manuscript hash mismatch")
    if receipt.get("rawCredentialExposed") is not False or receipt.get("rawProviderTokenExposed") is not False:
        raise ValidationError("humanizerQualityReceiptPath: provider credential/token exposure flag is not false")
    metrics = receipt.get("metrics") if isinstance(receipt.get("metrics"), dict) else {}
    if float(metrics.get("sourceContentOverlapRatio") or 0) < 0.52:
        raise ValidationError("humanizerQualityReceiptPath: source overlap ratio is below the accepted floor")
    if int(metrics.get("fusedArtifactCount") or 0) != 0:
        raise ValidationError("humanizerQualityReceiptPath: fused spacing artifacts are present")


def _accepted_humanized_manuscript_hash(path: Path, fallback_hash: str) -> str:
    receipt = _read_json(path)
    accepted = _string(receipt.get("acceptedHumanizedManuscriptSha256"))
    if accepted:
        return accepted
    quality = receipt.get("quality") if isinstance(receipt.get("quality"), dict) else {}
    accepted = _string(quality.get("candidateTextSha256"))
    return accepted or fallback_hash


def _validate_cover_receipt(path: Path, cover_hash: str, project_id: str, manuscript_hash: str) -> None:
    _validate_receipt(
        path=path,
        label="storySceneCoverReceiptPath",
        operation="selected_face_scene_render",
        provider_token=None,
        artifact_hashes=(cover_hash,),
        required_tokens=(
            _owner_path(project_id),
            _owner_path(project_id, "cover"),
            "selected_character_face",
        ),
        external=True,
    )
    receipt = _read_json(path)
    if not (
        _contains_token(receipt, "story_scene")
        or _contains_token(receipt, "scene_excerpt_sha256")
        or _contains_token(receipt, manuscript_hash)
    ):
        raise ValidationError("storySceneCoverReceiptPath: cover must be bound to an actual story scene")


def _validate_audio_job_receipt(path: Path, audiobook_hash: str, share_url: str) -> str:
    receipt = _read_json(path)
    _reject_fake_markers(receipt, "eaAudiobookJobReceiptPath")
    _reject_raw_evidence_leaks(receipt, "eaAudiobookJobReceiptPath")
    if _string(receipt.get("contract_name")) != EA_JOB_RECEIPT_CONTRACT_NAME:
        raise ValidationError("eaAudiobookJobReceiptPath: unsupported contract")
    if _string(receipt.get("status")) != "audiobookshelf_imported":
        raise ValidationError("eaAudiobookJobReceiptPath: job is not audiobookshelf_imported")
    render = receipt.get("render") if isinstance(receipt.get("render"), dict) else {}
    assembly = receipt.get("assembly") if isinstance(receipt.get("assembly"), dict) else {}
    imported = receipt.get("audiobookshelf_import") if isinstance(receipt.get("audiobookshelf_import"), dict) else {}
    privacy = receipt.get("privacy") if isinstance(receipt.get("privacy"), dict) else {}
    provider = _string(render.get("provider"))
    if not _provider_allowed(provider, APPROVED_AUDIO_PROVIDERS):
        raise ValidationError("eaAudiobookJobReceiptPath: audio provider must be Inkfluence or Unmixr")
    if assembly.get("output_file_ready") is not True:
        raise ValidationError("eaAudiobookJobReceiptPath: assembled audiobook is not ready")
    if audiobook_hash not in {_string(assembly.get("output_file_sha256")), _string(imported.get("target_file_sha256"))}:
        raise ValidationError("eaAudiobookJobReceiptPath: audiobook hash does not match receipt")
    if _string(imported.get("status")) != "imported" or imported.get("target_file_ready") is not True:
        raise ValidationError("eaAudiobookJobReceiptPath: Audiobookshelf import target is not ready")
    if _string(imported.get("player_scoped_reference_status")) != "signed_reference_ready":
        raise ValidationError("eaAudiobookJobReceiptPath: player-scoped reference is not ready")
    if _string(imported.get("public_share_status")) != "public_share_ready":
        raise ValidationError("eaAudiobookJobReceiptPath: public share is not ready")
    if _string(imported.get("public_share_url")) != share_url:
        raise ValidationError("eaAudiobookJobReceiptPath: public share URL does not match manifest")
    if _string(imported.get("public_share_telegram_delivery_status")) != "sent":
        raise ValidationError("eaAudiobookJobReceiptPath: Telegram public-share delivery was not sent")
    if imported.get("public_share_telegram_message_id_present") is not True:
        raise ValidationError("eaAudiobookJobReceiptPath: Telegram message proof is missing")
    if _string(imported.get("public_share_playback_e2e_status")) != "pass":
        raise ValidationError("eaAudiobookJobReceiptPath: machine playback E2E did not pass")
    if int(imported.get("public_share_playback_e2e_track_response_status") or 0) not in {200, 206}:
        raise ValidationError("eaAudiobookJobReceiptPath: playback track response was not audio-ready")
    if not _string(imported.get("public_share_playback_e2e_track_content_type")).lower().startswith("audio/"):
        raise ValidationError("eaAudiobookJobReceiptPath: playback track content type is not audio")
    if float(imported.get("public_share_playback_e2e_duration_seconds") or 0) <= 0:
        raise ValidationError("eaAudiobookJobReceiptPath: playback duration is missing")
    if float(imported.get("public_share_playback_e2e_current_time_after_play_seconds") or 0) <= 0:
        raise ValidationError("eaAudiobookJobReceiptPath: playback did not advance")
    if imported.get("public_share_playback_e2e_media_error_present") is True:
        raise ValidationError("eaAudiobookJobReceiptPath: playback reported a media error")
    for key in (
        "public_share_token_exposed",
        "public_share_raw_library_path_exposed",
        "public_share_telegram_callback_tokens_exposed",
        "public_share_telegram_audiobookshelf_token_exposed",
    ):
        if imported.get(key) is True:
            raise ValidationError(f"eaAudiobookJobReceiptPath: {key} is exposed")
    for key, value in privacy.items():
        if key.endswith("_exposed") and value is True:
            raise ValidationError(f"eaAudiobookJobReceiptPath: privacy leak {key}")
    return provider


def _validate_m4b_provider_import_receipt(
    path: Path,
    *,
    audiobook_hash: str,
    cover_hash: str,
    manuscript_hash: str,
    origin_namespace: str,
) -> None:
    receipt = _read_json(path)
    _reject_fake_markers(receipt, "eaM4bProviderImportReceiptPath")
    _reject_raw_evidence_leaks(receipt, "eaM4bProviderImportReceiptPath")
    if _string(receipt.get("contractName")) != EA_M4B_PROVIDER_IMPORT_CONTRACT_NAME:
        raise ValidationError("eaM4bProviderImportReceiptPath: unsupported contract")
    if _string(receipt.get("status")) != "pass":
        raise ValidationError("eaM4bProviderImportReceiptPath: M4B provider import gate is not pass")
    if receipt.get("goldEligible") is not True:
        raise ValidationError("eaM4bProviderImportReceiptPath: M4B provider import gate is not gold eligible")
    if receipt.get("issues") not in ([], None):
        raise ValidationError("eaM4bProviderImportReceiptPath: M4B provider import gate has issues")
    if _string(receipt.get("namespace")) != origin_namespace:
        raise ValidationError("eaM4bProviderImportReceiptPath: Origin namespace mismatch")
    if _string(receipt.get("m4bSha256")) != audiobook_hash:
        raise ValidationError("eaM4bProviderImportReceiptPath: M4B hash mismatch")
    if _string(receipt.get("coverSha256")) != cover_hash:
        raise ValidationError("eaM4bProviderImportReceiptPath: cover hash mismatch")
    if _string(receipt.get("sourceSha256")) != manuscript_hash:
        raise ValidationError("eaM4bProviderImportReceiptPath: manuscript/source hash mismatch")
    if receipt.get("rawRuntimePathsExposed") is not False:
        raise ValidationError("eaM4bProviderImportReceiptPath: raw runtime paths are exposed")
    if receipt.get("rawCredentialExposed") is not False or receipt.get("rawProviderTokenExposed") is not False:
        raise ValidationError("eaM4bProviderImportReceiptPath: provider credential/token exposure flag is not false")
    if not _contains_token(receipt, "provider_m4b_verified") or not _contains_token(receipt, "m4b_cover_embedded"):
        raise ValidationError("eaM4bProviderImportReceiptPath: provider M4B/cover verification tokens missing")


def _validate_live_delivery_receipt(
    path: Path,
    *,
    project_id: str,
    base_url: str,
    share_url: str,
    origin_namespace: str,
) -> dict[str, Any]:
    receipt = _read_json(path)
    _reject_fake_markers(receipt, "eaTelegramLiveDeliveryReceiptPath")
    _reject_raw_evidence_leaks(receipt, "eaTelegramLiveDeliveryReceiptPath")
    if _string(receipt.get("contract_name")) != EA_LIVE_DELIVERY_CONTRACT_NAME:
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: unsupported contract")
    if _string(receipt.get("status")) != "pass":
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: live delivery status is not pass")
    if receipt.get("live_delivery_claim_allowed") is not True:
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: live delivery claim is not allowed")
    if receipt.get("machine_playback_e2e_verified") is not True:
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: machine playback E2E was not verified")
    if receipt.get("failed_codes") not in ([], None):
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: failed codes are present")
    selected = receipt.get("selected_delivery") if isinstance(receipt.get("selected_delivery"), dict) else {}
    parsed_share = urlparse(share_url)
    if selected.get("public_share_url_present") is not True:
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: public share URL was not present in source job")
    if _string(selected.get("public_share_host")) != (parsed_share.hostname or ""):
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: public share host does not match manifest")
    if _string(selected.get("telegram_delivery_status")) != "sent":
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: Telegram delivery was not sent")
    if selected.get("telegram_delivery_message_id_present") is not True:
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: Telegram message proof is missing")
    link_bundle = selected.get("origin_edition_link_bundle") if isinstance(selected.get("origin_edition_link_bundle"), dict) else {}
    if _string(link_bundle.get("status")) not in {"sent", "pass", "delivered"}:
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: Origin Edition link bundle was not sent")
    if _string(link_bundle.get("project_id")) != project_id:
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: Origin Edition link bundle project mismatch")
    if _string(link_bundle.get("telegram_delivery_status")) != "sent":
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: Origin Edition link bundle Telegram delivery was not sent")
    if link_bundle.get("telegram_message_id_present") is not True:
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: Origin Edition link bundle message proof is missing")
    if link_bundle.get("all_required_links_present") is not True:
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: Origin Edition link bundle is missing required links")
    if link_bundle.get("raw_urls_exposed") is True:
        raise ValidationError("eaTelegramLiveDeliveryReceiptPath: Origin Edition link bundle exposes raw URLs")
    expected_links = {
        "read_url_sha256": origin_owner_url(base_url, project_id, "read"),
        "listen_url_sha256": origin_owner_url(base_url, project_id, "listen"),
        "watch_url_sha256": origin_owner_url(base_url, project_id, "video"),
        "open_in_chummer_url_sha256": origin_owner_url(base_url, project_id),
        "origin_namespace_sha256": origin_namespace,
    }
    for key, expected_value in expected_links.items():
        if _string(link_bundle.get(key)) != _sha256_text(expected_value):
            raise ValidationError(f"eaTelegramLiveDeliveryReceiptPath: Origin Edition link bundle hash mismatch for {key}")
    privacy = receipt.get("privacy") if isinstance(receipt.get("privacy"), dict) else {}
    for key in ("provider_secret_exposed", "audiobookshelf_token_exposed"):
        if privacy.get(key) is True:
            raise ValidationError(f"eaTelegramLiveDeliveryReceiptPath: privacy leak {key}")
    return receipt


def _materialize_normalized_receipts(
    *,
    output_dir: Path,
    project_id: str,
    audiobook_share_url: str,
    dossier_share_url: str,
    origin_namespace: str,
    audiobook_hash: str,
    audiobook_provider: str,
    ea_job_receipt_path: Path,
    ea_live_receipt_path: Path,
) -> tuple[Path, Path]:
    generated_at = _now_iso()
    job_receipt_hash = _sha256_file(ea_job_receipt_path)
    live_receipt_hash = _sha256_file(ea_live_receipt_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    audiobook_receipt_path = output_dir / f"{project_id}.audiobookshelf-import.receipt.json"
    telegram_receipt_path = output_dir / f"{project_id}.telegram-share.receipt.json"
    audiobook_receipt = {
        "operation": "audiobookshelf_import",
        "provider": "Audiobookshelf",
        "status": "verified",
        "completedAtUtc": generated_at,
        "artifactSha256": [audiobook_hash],
        "audiobookProvider": audiobook_provider,
        "audiobookshelfShareUrl": audiobook_share_url,
        "deliveredLinks": [
            LIVE_TOKEN,
            f"{PROVIDER_REFERENCE_TOKEN}:ea_job_receipt:{job_receipt_hash}",
            f"{PROVIDER_REFERENCE_TOKEN}:ea_live_delivery_receipt:{live_receipt_hash}",
            f"narrationProvider: {audiobook_provider}",
            "machine_playback_e2e_verified",
            audiobook_share_url,
        ],
        "evidence": {
            "eaJobReceiptSha256": job_receipt_hash,
            "eaLiveDeliveryReceiptSha256": live_receipt_hash,
            "eaJobReceiptContract": EA_JOB_RECEIPT_CONTRACT_NAME,
            "eaLiveDeliveryContract": EA_LIVE_DELIVERY_CONTRACT_NAME,
        },
    }
    telegram_receipt = {
        "operation": "telegram_share_delivery",
        "provider": "EA Telegram",
        "status": "delivered",
        "deliveredAtUtc": generated_at,
        "deliveredLinks": [
            _owner_path(project_id),
            _owner_path(project_id, "read"),
            _owner_path(project_id, "listen"),
            _owner_path(project_id, "watch"),
            origin_namespace,
            dossier_share_url,
            audiobook_share_url,
            LIVE_TOKEN,
            f"{PROVIDER_REFERENCE_TOKEN}:ea_live_delivery_receipt:{live_receipt_hash}",
            f"audiobookshelf_dossier_share_sha256:{hashlib.sha256(dossier_share_url.encode('utf-8')).hexdigest()}",
            f"audiobookshelf_audiobook_share_sha256:{hashlib.sha256(audiobook_share_url.encode('utf-8')).hexdigest()}",
        ],
        "evidence": {
            "eaLiveDeliveryReceiptSha256": live_receipt_hash,
            "publicShareUrlRedacted": True,
            "telegramMessageIdHashedByEa": True,
        },
    }
    _write_json(audiobook_receipt_path, audiobook_receipt)
    _write_json(telegram_receipt_path, telegram_receipt)
    return audiobook_receipt_path, telegram_receipt_path


def materialize(manifest_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    _reject_fake_markers(manifest, "manifest")
    project_id = _string(manifest.get("projectId"))
    if not project_id:
        raise ValidationError("projectId is required")
    if "/" in project_id or "\\" in project_id:
        raise ValidationError("projectId must be a route-safe identifier")
    audiobook_share_url = _string(manifest.get("audiobookshelfAudiobookShareUrl")) or _string(manifest.get("audiobookshelfShareUrl"))
    dossier_share_url = _string(manifest.get("audiobookshelfDossierShareUrl"))
    if not _trusted_audiobookshelf_share_url(audiobook_share_url):
        raise ValidationError("audiobookshelfAudiobookShareUrl must be a trusted chummer.run Audiobookshelf share URL")
    if not _trusted_audiobookshelf_share_url(dossier_share_url):
        raise ValidationError("audiobookshelfDossierShareUrl must be a trusted chummer.run Audiobookshelf share URL")
    family_name = _string(manifest.get("familyName"))
    given_name = _string(manifest.get("givenName"))
    runner_name = _string(manifest.get("runnerName")) or _string(manifest.get("runnerAlias")) or "Runner"
    origin_namespace = _string(manifest.get("originEditionNamespace"))
    if not origin_namespace:
        raise ValidationError("originEditionNamespace is required")
    if not origin_namespace.lower().startswith("origin.chummer.run/"):
        raise ValidationError("originEditionNamespace must start with origin.chummer.run/")
    context = OriginEditionContext.from_env(
        project_id=project_id,
        family_name=family_name,
        given_name=given_name,
        runner_name=runner_name,
        namespace=origin_namespace,
        base_url=_string(manifest.get("baseUrl") or manifest.get("chummerBaseUrl") or manifest.get("originEditionBaseUrl")),
    )
    base_url = context.base_url

    source_packet = _require_file(manifest.get("sourcePacketPath"), "sourcePacketPath")
    source_receipt = _require_file(manifest.get("sourcePacketReceiptPath"), "sourcePacketReceiptPath")
    provider_manuscript = _require_file(manifest.get("providerManuscriptPath"), "providerManuscriptPath")
    provider_receipt = _require_file(manifest.get("providerManuscriptReceiptPath"), "providerManuscriptReceiptPath")
    humanizer_receipt = _require_file(manifest.get("humanizerReceiptPath"), "humanizerReceiptPath")
    humanizer_quality_receipt = _require_file(
        manifest.get("humanizerQualityReceiptPath"),
        "humanizerQualityReceiptPath",
    )
    canon_receipt = _require_file(manifest.get("canonAuditReceiptPath"), "canonAuditReceiptPath")
    book_artifact = _require_file(manifest.get("bookArtifactPath"), "bookArtifactPath")
    book_receipt = _require_file(manifest.get("bookArtifactReceiptPath"), "bookArtifactReceiptPath")
    cover_artifact = _require_file(manifest.get("storySceneCoverPath"), "storySceneCoverPath")
    cover_receipt = _require_file(manifest.get("storySceneCoverReceiptPath"), "storySceneCoverReceiptPath")
    audiobook_artifact = _require_file(manifest.get("audiobookPath"), "audiobookPath")
    video_artifact = _require_file(manifest.get("dossierVideoPath"), "dossierVideoPath")
    video_receipt = _require_file(manifest.get("dossierVideoReceiptPath"), "dossierVideoReceiptPath")
    final_no_fallback_receipt = _require_file(
        manifest.get(
            "finalNoFallbackNoSentinelAuditReceiptPath",
            f"{origin_namespace}/final-no-fallback-no-sentinel-audit.receipt.json",
        ),
        "finalNoFallbackNoSentinelAuditReceiptPath",
    )
    ea_job_receipt = _require_file(manifest.get("eaAudiobookJobReceiptPath"), "eaAudiobookJobReceiptPath")
    ea_m4b_provider_receipt = _require_file(
        manifest.get("eaM4bProviderImportReceiptPath"),
        "eaM4bProviderImportReceiptPath",
    )
    ea_live_delivery_receipt = _require_file(
        manifest.get("eaTelegramLiveDeliveryReceiptPath"),
        "eaTelegramLiveDeliveryReceiptPath",
    )

    source_hash = _sha256_file(source_packet)
    manuscript_hash = _sha256_file(provider_manuscript)
    accepted_manuscript_hash = _accepted_humanized_manuscript_hash(humanizer_receipt, manuscript_hash)
    book_hash = _sha256_file(book_artifact)
    cover_hash = _sha256_file(cover_artifact)
    audiobook_hash = _sha256_file(audiobook_artifact)
    video_hash = _sha256_file(video_artifact)

    _validate_receipt(
        path=source_receipt,
        label="sourcePacketReceiptPath",
        operation="origin_source_packet_approval",
        provider_token="Chummer",
        artifact_hashes=(source_hash,),
        required_tokens=("approved_source_packet", "external_processing_consent"),
    )
    _validate_provider_manuscript_receipt(provider_receipt, manuscript_hash)
    _validate_receipt(
        path=humanizer_receipt,
        label="humanizerReceiptPath",
        operation="undetectable_humanizer_postprocess",
        provider_token="Undetectable",
        artifact_hashes=(manuscript_hash,),
        external=True,
    )
    _validate_humanizer_quality_receipt(humanizer_quality_receipt, manuscript_hash)
    _validate_receipt(
        path=canon_receipt,
        label="canonAuditReceiptPath",
        operation="chummer_canon_audit",
        provider_token="Chummer",
        artifact_hashes=(source_hash, manuscript_hash),
        required_tokens=("canon_audit_passed", "hard_conflicts:0", "privacy_findings:0"),
    )
    _validate_receipt(
        path=book_receipt,
        label="bookArtifactReceiptPath",
        operation="book_artifact_import",
        provider_token=None,
        artifact_hashes=(book_hash,),
        external=True,
    )
    _validate_cover_receipt(cover_receipt, cover_hash, project_id, accepted_manuscript_hash)
    _validate_receipt(
        path=video_receipt,
        label="dossierVideoReceiptPath",
        operation="dossier_video_import",
        provider_token=None,
        artifact_hashes=(video_hash,),
        external=True,
    )
    audiobook_provider = _validate_audio_job_receipt(ea_job_receipt, audiobook_hash, audiobook_share_url)
    _validate_m4b_provider_import_receipt(
        ea_m4b_provider_receipt,
        audiobook_hash=audiobook_hash,
        cover_hash=cover_hash,
        manuscript_hash=accepted_manuscript_hash,
        origin_namespace=origin_namespace,
    )
    live_receipt = _validate_live_delivery_receipt(
        ea_live_delivery_receipt,
        project_id=project_id,
        base_url=base_url,
        share_url=audiobook_share_url,
        origin_namespace=origin_namespace,
    )

    resolved_output = output_path or manifest_path.with_name(DEFAULT_OUTPUT_NAME)
    normalized_dir = resolved_output.parent / origin_namespace / "audiobook"
    audiobook_receipt, telegram_receipt = _materialize_normalized_receipts(
        output_dir=normalized_dir,
        project_id=project_id,
        audiobook_share_url=audiobook_share_url,
        dossier_share_url=dossier_share_url,
        origin_namespace=origin_namespace,
        audiobook_hash=audiobook_hash,
        audiobook_provider=audiobook_provider,
        ea_job_receipt_path=ea_job_receipt,
        ea_live_receipt_path=ea_live_delivery_receipt,
    )
    owner_url = origin_owner_url(base_url, project_id)
    import_request = {
        "projectId": project_id,
        "title": _string(manifest.get("title")) or "Origin Dossier",
        "runnerAlias": _string(manifest.get("runnerAlias")) or "Runner",
        "familyName": family_name,
        "givenName": given_name,
        "runnerName": runner_name,
        "originEditionNamespace": origin_namespace,
        "publicationState": "published_for_owner",
        "bookArtifactUrl": origin_owner_url(base_url, project_id, "book"),
        "audiobookshelfShareUrl": audiobook_share_url,
        "audiobookshelfDossierShareUrl": dossier_share_url,
        "audiobookshelfAudiobookShareUrl": audiobook_share_url,
        "dossierVideoUrl": origin_owner_url(base_url, project_id, "video"),
        "storySceneCoverUrl": origin_owner_url(base_url, project_id, "cover"),
        "providerAuthoredManuscriptImported": True,
        "undetectableHumanizerApplied": True,
        "bookArtifactVerified": True,
        "dossierVideoVerified": True,
        "storySceneCoverUsesSelectedCharacterFace": True,
        "audiobookshelfPlaybackVerified": True,
        "telegramShareDelivered": True,
        "sourcePacketPath": str(source_packet),
        "sourcePacketReceiptPath": str(source_receipt),
        "canonAuditReceiptPath": str(canon_receipt),
        "providerManuscriptPath": str(provider_manuscript),
        "providerManuscriptReceiptPath": str(provider_receipt),
        "humanizerReceiptPath": str(humanizer_receipt),
        "humanizerQualityReceiptPath": str(humanizer_quality_receipt),
        "bookArtifactPath": str(book_artifact),
        "bookArtifactReceiptPath": str(book_receipt),
        "storySceneCoverPath": str(cover_artifact),
        "storySceneCoverReceiptPath": str(cover_receipt),
        "audiobookPath": str(audiobook_artifact),
        "m4bProviderImportReceiptPath": str(ea_m4b_provider_receipt),
        "audiobookshelfImportReceiptPath": str(audiobook_receipt),
        "dossierVideoPath": str(video_artifact),
        "dossierVideoReceiptPath": str(video_receipt),
        "telegramShareDeliveryReceiptPath": str(telegram_receipt),
        "finalNoFallbackNoSentinelAuditReceiptPath": str(final_no_fallback_receipt),
        "missingGoldRequirements": [],
    }
    result = {
        "contractName": CONTRACT_NAME,
        "status": "pass",
        "generatedAtUtc": _now_iso(),
        "goalCompletionClaimAllowed": False,
        "claim": "This materializes a Chummer import payload from live Origin Dossier artifact evidence; it is not itself provider generation or user playback proof.",
        "chummerRunOwnerUrl": owner_url,
        "audiobookshelfShareUrl": audiobook_share_url,
        "audiobookshelfDossierShareUrl": dossier_share_url,
        "audiobookshelfAudiobookShareUrl": audiobook_share_url,
        "audiobookProvider": audiobook_provider,
        "realUserPlaybackAcceptanceVerified": _bool(live_receipt.get("real_user_playback_acceptance_verified")),
        "evidence": {
            "sourcePacketSha256": source_hash,
            "providerManuscriptSha256": manuscript_hash,
            "acceptedHumanizedManuscriptSha256": accepted_manuscript_hash,
            "humanizerQualityReceiptSha256": _sha256_file(humanizer_quality_receipt),
            "bookArtifactSha256": book_hash,
            "storySceneCoverSha256": cover_hash,
            "audiobookSha256": audiobook_hash,
            "dossierVideoSha256": video_hash,
            "eaAudiobookJobReceiptSha256": _sha256_file(ea_job_receipt),
            "eaM4bProviderImportReceiptSha256": _sha256_file(ea_m4b_provider_receipt),
            "eaTelegramLiveDeliveryReceiptSha256": _sha256_file(ea_live_delivery_receipt),
            "normalizedAudiobookshelfImportReceiptPath": str(audiobook_receipt),
            "normalizedTelegramShareDeliveryReceiptPath": str(telegram_receipt),
        },
        "importRequest": import_request,
    }
    _write_json(resolved_output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize a Chummer Origin Dossier live artifact import request.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", "--out", dest="output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        result = materialize(args.manifest, args.output)
    except ValidationError as exc:
        print(json.dumps({"contractName": CONTRACT_NAME, "status": "failed", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
