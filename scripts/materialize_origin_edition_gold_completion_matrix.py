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


CONTRACT_NAME = "chummer.origin_edition.gold_completion_matrix.v1"
DEFAULT_EVIDENCE_ROOT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold")
REQUIRED_COVER_SURFACES = (
    "chummer_hero_cover",
    "dossier_cover_asset",
    "ebook_embedded_cover",
    "pdf_cover_embedding",
    "audiobook_cover_asset",
    "m4b_cover_embedding",
    "audiobookshelf_dossier_cover",
    "audiobookshelf_audiobook_cover",
    "movie_poster",
)
REQUIRED_FINAL_BUNDLE_SURFACES = (
    "approved_canon_packet",
    "provider_manuscript",
    "humanizer_receipt",
    "humanizer_quality_receipt",
    "cover",
    "ebook",
    "pdf",
    "pdf_cover_receipt",
    "dossier_audiobookshelf_receipt",
    "m4b_provider_gate",
    "cover_consistency",
    "movie",
    "movie_receipt",
    "real_m4b_artifact",
    "audiobookshelf_audiobook_receipt",
)
FORBIDDEN_RECEIPT_SECRET_MARKERS = (
    "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN=",
    "Bearer ",
    "secret-token",
    "owner-session-token",
    "secret-session",
    "super-secret",
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def string(value: object) -> str:
    return str(value or "").strip()


def is_pass(payload: dict[str, Any]) -> bool:
    return string(payload.get("status")).lower() in {"pass", "approved", "verified", "delivered", "published", "generated"}


def artifact_exists(live_import_path: Path, raw_path: object) -> bool:
    value = string(raw_path)
    if not value:
        return False
    path = Path(value)
    if not path.is_absolute():
        path = live_import_path.parent / path
    return path.is_file() and path.stat().st_size > 0


def relative_path(raw_path: object) -> str:
    value = string(raw_path).replace("\\", "/").lstrip("/")
    marker = "origin.chummer.run/"
    if marker in value:
        value = value[value.index(marker) :]
    return value


def path_under(raw_path: object, expected_prefix: str, *, suffixes: tuple[str, ...] = ()) -> bool:
    value = relative_path(raw_path)
    prefix = expected_prefix.rstrip("/") + "/"
    if not value.startswith(prefix):
        return False
    return not suffixes or value.lower().endswith(tuple(item.lower() for item in suffixes))


def receipt_row(row_id: str, label: str, path: Path, *, pass_status_required: bool = True) -> dict[str, Any]:
    row: dict[str, Any] = {"id": row_id, "label": label, "path": path.as_posix()}
    if not path.is_file():
        row["status"] = "missing"
        row["evidence"] = "receipt_missing"
        return row
    payload = read_json(path)
    row["sha256"] = sha256_file(path)
    row["reportedStatus"] = payload.get("status")
    row["contractName"] = payload.get("contractName") or payload.get("contract_name")
    if pass_status_required and not is_pass(payload):
        row["status"] = "blocked"
        row["evidence"] = "receipt_not_pass"
    else:
        row["status"] = "proved"
        row["evidence"] = "receipt_present"
    if payload.get("goldEligible") is False:
        row["goldEligible"] = False
    if payload.get("goalCompletionClaimAllowed") is False:
        row["goalCompletionClaimAllowed"] = False
    if isinstance(payload.get("blockers"), list):
        row["blockers"] = payload["blockers"]
    if isinstance(payload.get("failedCodes"), list):
        row["failedCodes"] = payload["failedCodes"]
    return row


def bool_row(row_id: str, label: str, value: bool, evidence: str) -> dict[str, Any]:
    return {
        "id": row_id,
        "label": label,
        "status": "proved" if value else "blocked",
        "evidence": evidence,
    }


def cover_surface_row(path: Path) -> dict[str, Any]:
    flags = {surface: False for surface in REQUIRED_COVER_SURFACES}
    row: dict[str, Any] = {
        "id": "cover_consistency_required_surfaces",
        "label": "Same rendered story-scene cover is proved across ebook, PDF, M4B, Audiobookshelf, movie poster, and Chummer hero",
        "path": path.as_posix(),
        "flags": flags,
    }
    if not path.is_file():
        row["status"] = "missing"
        row["evidence"] = "receipt_missing"
        return row
    payload = read_json(path)
    row["sha256"] = sha256_file(path)
    row["reportedStatus"] = payload.get("status")
    row["expectedCoverSha256"] = payload.get("expectedCoverSha256")
    surfaces = payload.get("surfaces") if isinstance(payload.get("surfaces"), list) else []
    by_name = {string(surface.get("name")): surface for surface in surfaces if isinstance(surface, dict)}
    for surface in REQUIRED_COVER_SURFACES:
        flags[surface] = string(by_name.get(surface, {}).get("status")).lower() == "pass"
    blocked = [surface for surface, passed in flags.items() if not passed]
    row["blockedSurfaces"] = blocked
    row["status"] = "proved" if string(payload.get("status")).lower() == "pass" and not blocked else "blocked"
    row["evidence"] = "strict_cover_surface_matrix"
    if payload.get("goldEligible") is False:
        row["goldEligible"] = False
    return row


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def telegram_link_bundle_row(path: Path, project_id: str, base_url: str) -> dict[str, Any]:
    expected = {
        "read_url_sha256": origin_owner_url(base_url, project_id, "/read"),
        "listen_url_sha256": origin_owner_url(base_url, project_id, "/listen"),
        "watch_url_sha256": origin_owner_url(base_url, project_id, "/video"),
        "open_in_chummer_url_sha256": origin_owner_url(base_url, project_id),
    }
    flags = {
        "telegram_receipt_present": path.is_file(),
        "telegram_delivery_status_sent": False,
        "telegram_message_id_present": False,
        "all_required_links_present": False,
        "raw_urls_not_exposed": False,
        "read_link_hash_matches": False,
        "listen_link_hash_matches": False,
        "watch_link_hash_matches": False,
        "open_in_chummer_link_hash_matches": False,
    }
    row: dict[str, Any] = {
        "id": "telegram_origin_links_verified",
        "label": "EA Telegram sent read, listen, watch, and open-in-Chummer Origin links",
        "path": path.as_posix(),
        "flags": flags,
    }
    if not path.is_file():
        row["status"] = "missing"
        row["evidence"] = "receipt_missing"
        return row
    payload = read_json(path)
    selected = payload.get("selected_delivery") if isinstance(payload.get("selected_delivery"), dict) else {}
    bundle = selected.get("origin_edition_link_bundle") if isinstance(selected.get("origin_edition_link_bundle"), dict) else {}
    row["sha256"] = sha256_file(path)
    row["reportedStatus"] = payload.get("status")
    flags["telegram_delivery_status_sent"] = string(bundle.get("telegram_delivery_status")) == "sent"
    flags["telegram_message_id_present"] = bundle.get("telegram_message_id_present") is True
    flags["all_required_links_present"] = bundle.get("all_required_links_present") is True
    flags["raw_urls_not_exposed"] = bundle.get("raw_urls_exposed") is not True
    flags["read_link_hash_matches"] = string(bundle.get("read_url_sha256")) == sha256_text(expected["read_url_sha256"])
    flags["listen_link_hash_matches"] = string(bundle.get("listen_url_sha256")) == sha256_text(expected["listen_url_sha256"])
    flags["watch_link_hash_matches"] = string(bundle.get("watch_url_sha256")) == sha256_text(expected["watch_url_sha256"])
    flags["open_in_chummer_link_hash_matches"] = string(bundle.get("open_in_chummer_url_sha256")) == sha256_text(expected["open_in_chummer_url_sha256"])
    failed = [key for key, passed in flags.items() if not passed]
    row["failedFlags"] = failed
    row["status"] = "proved" if not failed else "blocked"
    row["evidence"] = "ea_telegram_origin_link_bundle"
    return row


def tokens(payload: dict[str, Any]) -> set[str]:
    values = payload.get("tokens") if isinstance(payload.get("tokens"), list) else []
    return {string(value) for value in values}


def canon_authority_row(source_receipt_path: Path, canon_receipt_path: Path) -> dict[str, Any]:
    flags = {
        "source_receipt_present": source_receipt_path.is_file(),
        "canon_receipt_present": canon_receipt_path.is_file(),
        "source_packet_approved": False,
        "external_processing_consented": False,
        "source_privacy_review_passed": False,
        "approved_sample_runner_canon_only": False,
        "canon_audit_passed": False,
        "hard_conflicts_zero": False,
        "privacy_findings_zero": False,
        "no_provider_created_facts_entered_canon": False,
    }
    row: dict[str, Any] = {
        "id": "chummer_canon_authority_verified",
        "label": "Chummer owns canon and no provider-created facts entered runner canon",
        "sourceReceiptPath": source_receipt_path.as_posix(),
        "canonReceiptPath": canon_receipt_path.as_posix(),
        "flags": flags,
    }
    source_payload = read_json(source_receipt_path) if source_receipt_path.is_file() else {}
    canon_payload = read_json(canon_receipt_path) if canon_receipt_path.is_file() else {}
    source_tokens = tokens(source_payload)
    canon_tokens = tokens(canon_payload)
    if source_receipt_path.is_file():
        row["sourceReceiptSha256"] = sha256_file(source_receipt_path)
    if canon_receipt_path.is_file():
        row["canonReceiptSha256"] = sha256_file(canon_receipt_path)
    flags["source_packet_approved"] = "approved_source_packet" in source_tokens and is_pass(source_payload)
    flags["external_processing_consented"] = "external_processing_consent" in source_tokens
    flags["source_privacy_review_passed"] = "privacy_review_passed" in source_tokens
    flags["approved_sample_runner_canon_only"] = (
        "approved_sample_runner_canon_only" in source_tokens
        and "approved_sample_runner_canon_only" in canon_tokens
    )
    flags["canon_audit_passed"] = "canon_audit_passed" in canon_tokens and is_pass(canon_payload)
    flags["hard_conflicts_zero"] = (
        canon_payload.get("hardConflicts") == 0
        or "hard_conflicts:0" in canon_tokens
    )
    flags["privacy_findings_zero"] = (
        canon_payload.get("privacyFindings") == 0
        or "privacy_findings:0" in canon_tokens
    )
    flags["no_provider_created_facts_entered_canon"] = "no_provider_created_facts_entered_canon" in canon_tokens
    failed = [key for key, passed in flags.items() if not passed]
    row["failedFlags"] = failed
    row["status"] = "proved" if not failed else "blocked"
    row["evidence"] = "chummer_source_packet_and_canon_audit_tokens"
    return row


def source_packet_integrity_row(live_import_path: Path, request: dict[str, Any], live_evidence: dict[str, Any]) -> dict[str, Any]:
    source_path = (
        Path(string(request.get("sourcePacketPath")))
        if string(request.get("sourcePacketPath")).startswith("/")
        else live_import_path.parent / string(request.get("sourcePacketPath"))
    )
    source_receipt_path = (
        Path(string(request.get("sourcePacketReceiptPath")))
        if string(request.get("sourcePacketReceiptPath")).startswith("/")
        else live_import_path.parent / string(request.get("sourcePacketReceiptPath") or "source-packet-approval.receipt.json")
    )
    canon_receipt_path = (
        Path(string(request.get("canonAuditReceiptPath")))
        if string(request.get("canonAuditReceiptPath")).startswith("/")
        else live_import_path.parent / string(request.get("canonAuditReceiptPath") or "canon-privacy-audit.receipt.json")
    )
    source_packet = read_json(source_path) if source_path.is_file() else {}
    source_receipt = read_json(source_receipt_path) if source_receipt_path.is_file() else {}
    canon_receipt = read_json(canon_receipt_path) if canon_receipt_path.is_file() else {}
    source_tokens = tokens(source_receipt)
    canon_tokens = tokens(canon_receipt)
    expected_source_sha = string(live_evidence.get("sourcePacketSha256"))
    actual_source_sha = sha256_file(source_path) if source_path.is_file() else ""
    prohibited = source_packet.get("prohibitedInventions") if isinstance(source_packet.get("prohibitedInventions"), list) else []
    prohibited_text = "\n".join(string(item) for item in prohibited)
    flags = {
        "source_packet_present": source_path.is_file(),
        "source_packet_sha_matches_import": actual_source_sha == expected_source_sha,
        "source_receipt_present": source_receipt_path.is_file(),
        "source_receipt_verified": is_pass(source_receipt),
        "source_receipt_sha_matches_packet": contains_value(source_receipt.get("artifactSha256"), expected_source_sha),
        "canon_receipt_present": canon_receipt_path.is_file(),
        "canon_receipt_verified": is_pass(canon_receipt),
        "canon_audit_includes_source_packet_sha": contains_value(canon_receipt.get("artifactSha256"), expected_source_sha),
        "contract_is_approved_sample_runner_canon": string(source_packet.get("contractName")) == "chummer.origin_dossier.approved_sample_runner_canon.v1",
        "fictional_operator_sample": string(source_packet.get("privacyClassification")) == "operator_owned_fictional_sample",
        "external_processing_consented_in_packet": source_packet.get("externalProcessingConsent") is True,
        "external_processing_consented_in_receipt": "external_processing_consent" in source_tokens,
        "chummer_owns_facts": string(source_packet.get("canonOwnsFacts")) == "Chummer",
        "approved_sample_runner_canon_only": "approved_sample_runner_canon_only" in source_tokens and "approved_sample_runner_canon_only" in canon_tokens,
        "privacy_review_passed": "privacy_review_passed" in source_tokens and canon_receipt.get("privacyFindings") == 0,
        "hard_conflicts_zero": canon_receipt.get("hardConflicts") == 0,
        "no_provider_created_facts_canonical": "no_provider_created_facts_entered_canon" in canon_tokens,
        "prohibited_inventions_present": len(prohibited) >= 5,
        "prohibits_game_fact_invention": "Do not add new game qualities, skills, equipment, contacts, enemies, or debts." in prohibited_text,
        "prohibits_provider_created_canon": "Do not make provider-created facts canonical." in prohibited_text,
        "selected_character_face_present": isinstance(source_packet.get("selectedCharacterFace"), dict) and bool(source_packet["selectedCharacterFace"].get("faceRef")),
        "story_scene_for_cover_present": isinstance(source_packet.get("storySceneForCover"), dict) and bool(source_packet["storySceneForCover"].get("sceneId")),
    }
    failed = [key for key, passed in flags.items() if not passed]
    return {
        "id": "source_packet_integrity_and_consent_verified",
        "label": "Approved sample runner source packet is hash-bound, consented, fictional, Chummer-owned, and canon-audited",
        "status": "proved" if not failed else "blocked",
        "evidence": "source_packet_approval_and_canon_audit_receipts",
        "flags": flags,
        "failedFlags": failed,
        "sourcePacketPath": source_path.as_posix(),
        "sourceReceiptPath": source_receipt_path.as_posix(),
        "canonReceiptPath": canon_receipt_path.as_posix(),
        "sourcePacketSha256": actual_source_sha,
        "sourceReceiptSha256": sha256_file(source_receipt_path) if source_receipt_path.is_file() else "",
        "canonReceiptSha256": sha256_file(canon_receipt_path) if canon_receipt_path.is_file() else "",
    }


def runsite_handoff_row(path: Path) -> dict[str, Any]:
    flags = {
        "receipt_present": path.is_file(),
        "receipt_passed": False,
        "integration_eligible": False,
        "ltd_inventory_inspected": False,
        "runsite_env_inspected": False,
        "ea_env_inspected": False,
        "rybbit_run_keys_present": False,
        "runsite_handoff_verified": False,
        "newest_ltds_inspected_top_level": False,
        "env_inspected_top_level": False,
        "rybbit_env_only_top_level": False,
        "secret_values_not_stored": False,
        "required_provider_inventory_signals_present": False,
        "required_files_passed": False,
        "deployment_not_performed": True,
        "goal_completion_not_claimed": False,
    }
    row: dict[str, Any] = {
        "id": "runsite_handoff_constraints_verified",
        "label": "RunSite handoff constraints, newest LTD/env inspection, Rybbit env-only wiring, and no-deploy posture are proved",
        "path": path.as_posix(),
        "flags": flags,
    }
    if not path.is_file():
        row["status"] = "missing"
        row["evidence"] = "receipt_missing"
        row["failedFlags"] = [key for key, passed in flags.items() if not passed]
        return row
    payload = read_json(path)
    inventory = payload.get("inventoryInspection") if isinstance(payload.get("inventoryInspection"), dict) else {}
    provider_signals = inventory.get("newestProviderInventorySignals") if isinstance(inventory.get("newestProviderInventorySignals"), dict) else {}
    rybbit_keys = inventory.get("rybbitRunKeysPresent") if isinstance(inventory.get("rybbitRunKeysPresent"), dict) else {}
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    check_statuses = {
        string(check.get("name")): string(check.get("status")).lower()
        for check in checks
        if isinstance(check, dict)
    }
    required_check_names = {
        "runsite_handoff_constraints",
        "origin_dossier_authenticated_page",
        "origin_dossier_private_route_controller",
        "origin_publication_gold_gate_service",
        "rybbit_env_only_layout",
        "runsite_env_example_rybbit",
        "runsite_compose_rybbit",
        "newest_ltd_and_env_inputs_inspected",
        "live_import_request",
        "local_authenticated_route_proof",
        "final_no_sentinel_media_audit",
    }
    required_provider_names = {"unmixr", "inkfluence", "firstBook", "youbooks"}
    flags["receipt_passed"] = is_pass(payload)
    flags["integration_eligible"] = payload.get("integrationEligible") is True
    flags["ltd_inventory_inspected"] = inventory.get("ltdInventoryInspected") is True
    flags["runsite_env_inspected"] = inventory.get("runsiteEnvInspected") is True
    flags["ea_env_inspected"] = inventory.get("eaEnvInspected") is True
    flags["rybbit_run_keys_present"] = all(rybbit_keys.get(key) is True for key in (
        "RYBBIT_CHUMMER_RUN_SITE_ID",
        "RYBBIT_CHUMMER_RUN_SCRIPT_URL",
        "RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN",
        "RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY",
    ))
    flags["runsite_handoff_verified"] = payload.get("runsiteHandoffVerified") is True
    flags["newest_ltds_inspected_top_level"] = payload.get("newestLtdsInspected") is True
    flags["env_inspected_top_level"] = payload.get("envInspected") is True
    flags["rybbit_env_only_top_level"] = payload.get("rybbitEnvOnly") is True
    flags["secret_values_not_stored"] = payload.get("secretValuesStored") is False
    flags["required_provider_inventory_signals_present"] = all(provider_signals.get(key) is True for key in required_provider_names)
    flags["required_files_passed"] = all(check_statuses.get(name) == "pass" for name in required_check_names)
    flags["deployment_not_performed"] = payload.get("deploymentPerformed") is not True
    flags["goal_completion_not_claimed"] = payload.get("goalCompletionClaimAllowed") is False
    failed = [key for key, passed in flags.items() if not passed]
    row.update(
        {
            "status": "proved" if not failed else "blocked",
            "evidence": "runsite_integration_receipt_strict_handoff_matrix",
            "failedFlags": failed,
            "sha256": sha256_file(path),
            "requiredChecks": sorted(required_check_names),
            "requiredProviderSignals": sorted(required_provider_names),
        }
    )
    return row


def final_bundle_row(path: Path) -> dict[str, Any]:
    flags = {
        "receipt_present": path.is_file(),
        "status_pass": False,
        "gold_eligible": False,
        "raw_runtime_paths_not_exposed": False,
        "final_no_fallback_token_present": False,
        "all_required_surfaces_token_present": False,
        "blocked_surfaces_empty": False,
        "all_required_surfaces_present_and_passed": False,
    }
    row: dict[str, Any] = {
        "id": "final_bundle_no_fallback_no_sentinel_verified",
        "label": "Final bundle has no fallback audio, sentinel media, placeholders, or missing Origin Edition surfaces",
        "path": path.as_posix(),
        "flags": flags,
    }
    if not path.is_file():
        row["status"] = "missing"
        row["evidence"] = "receipt_missing"
        row["failedFlags"] = [key for key, passed in flags.items() if not passed]
        return row
    payload = read_json(path)
    surface_items = payload.get("surfaces") if isinstance(payload.get("surfaces"), list) else []
    surfaces = {
        string(item.get("name")): item
        for item in surface_items
        if isinstance(item, dict)
    }
    payload_tokens = tokens(payload)
    surface_flags = {
        name: string(surfaces.get(name, {}).get("status")).lower() == "pass"
        for name in REQUIRED_FINAL_BUNDLE_SURFACES
    }
    row["sha256"] = sha256_file(path)
    row["surfaceFlags"] = surface_flags
    row["reportedStatus"] = payload.get("status")
    row["blockedSurfaces"] = payload.get("blockedSurfaces", [])
    flags["status_pass"] = string(payload.get("status")).lower() == "pass"
    flags["gold_eligible"] = payload.get("goldEligible") is True
    flags["raw_runtime_paths_not_exposed"] = payload.get("rawRuntimePathsExposed") is False
    flags["final_no_fallback_token_present"] = "final_no_fallback_no_sentinel_audit" in payload_tokens
    flags["all_required_surfaces_token_present"] = "all_required_origin_edition_surfaces_passed" in payload_tokens
    flags["blocked_surfaces_empty"] = payload.get("blockedSurfaces") == []
    flags["all_required_surfaces_present_and_passed"] = all(surface_flags.values())
    failed = [key for key, passed in flags.items() if not passed]
    row["failedFlags"] = failed
    row["status"] = "proved" if not failed else "blocked"
    row["evidence"] = "final_no_fallback_bundle_surface_matrix"
    return row


def secret_hygiene_row(evidence_root: Path) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    env_example = repo_root / ".env.example"
    receipt_paths = sorted(
        path
        for path in evidence_root.rglob("*.json")
        if path.is_file()
    )
    flags = {
        "receipt_secret_marker_scan_clean": False,
        "env_example_present": False,
        "env_example_identity_token_blank": False,
        "env_values_not_scanned_or_stored": True,
    }
    receipt_findings: list[dict[str, str]] = []
    for path in receipt_paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in FORBIDDEN_RECEIPT_SECRET_MARKERS:
            if marker in text:
                receipt_findings.append({"path": path.as_posix(), "marker": marker})
    env_lines = env_example.read_text(encoding="utf-8", errors="replace").splitlines() if env_example.is_file() else []
    flags["receipt_secret_marker_scan_clean"] = not receipt_findings
    flags["env_example_present"] = env_example.is_file()
    flags["env_example_identity_token_blank"] = "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN=" in env_lines
    failed = [key for key, passed in flags.items() if not passed]
    return {
        "id": "secret_hygiene_verified",
        "label": "Generated receipts and env template do not expose credentials or owner-session tokens",
        "status": "proved" if not failed else "blocked",
        "evidence": "receipt_secret_marker_scan_and_env_example_contract",
        "flags": flags,
        "failedFlags": failed,
        "receiptFilesScanned": len(receipt_paths),
        "sourceFilesScanned": 1,
        "receiptFindings": receipt_findings,
        "sourceFindings": [],
    }


def truthy(value: object) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "allowed", "published"}
    return False


def find_direct_publish_signals(payload: object, path: str = "") -> list[str]:
    findings: list[str] = []
    dangerous_keys = {
        "directProviderPublishingAllowed",
        "directProviderPublish",
        "providerPublished",
        "publishedByProvider",
        "providerOwnsPublicationState",
    }
    if isinstance(payload, dict):
        for key, value in payload.items():
            current = f"{path}.{key}" if path else str(key)
            if key in dangerous_keys and truthy(value):
                findings.append(current)
            findings.extend(find_direct_publish_signals(value, current))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            findings.extend(find_direct_publish_signals(item, f"{path}[{index}]"))
    return findings


def provider_publish_boundary_row(evidence_root: Path, live_import: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    live_import_path = evidence_root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    provider_paths = [
        evidence_root / "provider-manuscript-import.receipt.json",
        evidence_root / "book-artifact-import.receipt.json",
        Path(string(request.get("m4bProviderImportReceiptPath"))) if string(request.get("m4bProviderImportReceiptPath")).startswith("/") else live_import_path.parent / string(request.get("m4bProviderImportReceiptPath")),
        Path(string(request.get("dossierVideoReceiptPath"))) if string(request.get("dossierVideoReceiptPath")).startswith("/") else live_import_path.parent / string(request.get("dossierVideoReceiptPath")),
    ]
    provider_paths.extend(sorted(evidence_root.rglob("*provider*.receipt.json")))
    provider_paths = sorted({path.resolve() for path in provider_paths if string(path)})
    direct_publish_findings: list[dict[str, str]] = []
    direct_publish_disallowed_evidence = False
    provider_receipts_present = True
    for path in provider_paths:
        if not path.is_file():
            provider_receipts_present = False
            direct_publish_findings.append({"path": path.as_posix(), "field": "receipt_missing"})
            continue
        payload = read_json(path)
        if payload.get("directProviderPublishingAllowed") is False:
            direct_publish_disallowed_evidence = True
        for field in find_direct_publish_signals(payload):
            direct_publish_findings.append({"path": path.as_posix(), "field": field})
    flags = {
        "provider_receipts_present": provider_receipts_present,
        "publication_state_chummer_owned": string(request.get("publicationState")) == "published_for_owner",
        "live_import_passed": is_pass(live_import),
        "missing_gold_requirements_empty": request.get("missingGoldRequirements") == [],
        "direct_provider_publish_disallowed_evidence_present": direct_publish_disallowed_evidence,
        "no_direct_provider_publish_signals": not direct_publish_findings,
    }
    failed = [key for key, passed in flags.items() if not passed]
    return {
        "id": "provider_publish_boundary_verified",
        "label": "Providers did not publish directly and Chummer owns final publication state",
        "status": "proved" if not failed else "blocked",
        "evidence": "provider_receipt_direct_publish_scan_and_chummer_publication_state",
        "flags": flags,
        "failedFlags": failed,
        "providerReceiptFilesScanned": len(provider_paths),
        "directPublishFindings": direct_publish_findings,
    }


def audiobookshelf_share_row(evidence_root: Path, branch: Path, request: dict[str, Any]) -> dict[str, Any]:
    audiobook_receipt_path = (
        Path(string(request.get("audiobookshelfImportReceiptPath")))
        if string(request.get("audiobookshelfImportReceiptPath")).startswith("/")
        else evidence_root / string(request.get("audiobookshelfImportReceiptPath"))
    )
    dossier_receipt_path = branch / "dossier/audiobookshelf-dossier-import.receipt.json"
    audiobook_receipt = read_json(audiobook_receipt_path) if audiobook_receipt_path.is_file() else {}
    dossier_receipt = read_json(dossier_receipt_path) if dossier_receipt_path.is_file() else {}
    audiobook_share_url = string(request.get("audiobookshelfAudiobookShareUrl") or request.get("audiobookshelfShareUrl"))
    dossier_share_url = string(request.get("audiobookshelfDossierShareUrl"))
    audiobook_receipt_share_url = string(audiobook_receipt.get("shareUrl") or audiobook_receipt.get("audiobookshelfShareUrl"))
    flags = {
        "audiobook_receipt_present": audiobook_receipt_path.is_file(),
        "dossier_receipt_present": dossier_receipt_path.is_file(),
        "audiobook_receipt_verified": is_pass(audiobook_receipt),
        "dossier_receipt_verified": is_pass(dossier_receipt),
        "audiobook_share_created": audiobook_receipt.get("shareCreated") is True or (is_pass(audiobook_receipt) and audiobook_receipt_share_url != ""),
        "audiobook_share_status_ready": string(audiobook_receipt.get("shareStatus")) == "public_share_ready" or (is_pass(audiobook_receipt) and is_trusted_audiobookshelf_share(audiobook_receipt_share_url)),
        "audiobook_share_url_matches_receipt": audiobook_share_url != "" and audiobook_share_url == audiobook_receipt_share_url,
        "dossier_share_url_matches_receipt": dossier_share_url != "" and dossier_share_url == string(dossier_receipt.get("audiobookshelfDossierShareUrl")),
        "audiobook_share_url_is_audiobookshelf": is_trusted_audiobookshelf_share(audiobook_share_url),
        "dossier_share_url_is_audiobookshelf": is_trusted_audiobookshelf_share(dossier_share_url),
        "audiobookshelf_playback_verified": request.get("audiobookshelfPlaybackVerified") is True,
    }
    failed = [key for key, passed in flags.items() if not passed]
    return {
        "id": "audiobookshelf_dossier_and_audiobook_share_verified",
        "label": "Audiobookshelf hosts and shares both the ebook dossier and M4B audiobook with playback proof",
        "status": "proved" if not failed else "blocked",
        "evidence": "audiobookshelf_dossier_and_audiobook_import_receipts",
        "flags": flags,
        "failedFlags": failed,
        "audiobookReceiptPath": audiobook_receipt_path.as_posix(),
        "dossierReceiptPath": dossier_receipt_path.as_posix(),
        "audiobookReceiptSha256": sha256_file(audiobook_receipt_path) if audiobook_receipt_path.is_file() else "",
        "dossierReceiptSha256": sha256_file(dossier_receipt_path) if dossier_receipt_path.is_file() else "",
        "audiobookShareUrlSha256": sha256_text(audiobook_share_url) if audiobook_share_url else "",
        "dossierShareUrlSha256": sha256_text(dossier_share_url) if dossier_share_url else "",
    }


def contains_value(values: object, expected: object) -> bool:
    expected_value = string(expected)
    if not expected_value:
        return False
    if isinstance(values, list):
        return expected_value in {string(value) for value in values}
    return string(values) == expected_value


def movie_playback_row(live_import_path: Path, request: dict[str, Any], live_evidence: dict[str, Any], context: OriginEditionContext) -> dict[str, Any]:
    receipt_path = (
        Path(string(request.get("dossierVideoReceiptPath")))
        if string(request.get("dossierVideoReceiptPath")).startswith("/")
        else live_import_path.parent / string(request.get("dossierVideoReceiptPath"))
    )
    artifact_path = (
        Path(string(request.get("dossierVideoPath")))
        if string(request.get("dossierVideoPath")).startswith("/")
        else live_import_path.parent / string(request.get("dossierVideoPath"))
    )
    receipt = read_json(receipt_path) if receipt_path.is_file() else {}
    proof = receipt.get("storySceneProof") if isinstance(receipt.get("storySceneProof"), dict) else {}
    project_id = string(request.get("projectId")) or context.project_id
    expected_video_url = origin_owner_url(context.base_url, project_id, "/video")
    flags = {
        "movie_receipt_present": receipt_path.is_file(),
        "movie_receipt_verified": is_pass(receipt),
        "movie_artifact_present": artifact_path.is_file() and artifact_path.stat().st_size > 0,
        "movie_verified_in_import": request.get("dossierVideoVerified") is True,
        "movie_url_is_chummer_video_route": string(request.get("dossierVideoUrl")) == expected_video_url,
        "movie_sha_matches_import_evidence": contains_value(receipt.get("artifactSha256"), live_evidence.get("dossierVideoSha256")),
        "poster_sha_matches_story_cover": string(receipt.get("posterSha256")) == string(live_evidence.get("storySceneCoverSha256")),
        "visual_cover_sha_matches_story_cover": string(receipt.get("visualSourceCoverSha256")) == string(live_evidence.get("storySceneCoverSha256")),
        "audio_sha_matches_m4b": string(receipt.get("audioSourceM4bSha256")) == string(live_evidence.get("audiobookSha256")),
        "accepted_manuscript_sha_matches": string(receipt.get("acceptedHumanizedManuscriptSha256")) == string(live_evidence.get("acceptedHumanizedManuscriptSha256")),
        "source_packet_sha_matches": string(receipt.get("sourcePacketSha256")) == string(live_evidence.get("sourcePacketSha256")),
        "uses_accepted_humanized_story_scene": proof.get("usesAcceptedHumanizedStoryScene") is True,
        "uses_selected_character_face_cover": proof.get("usesSelectedCharacterFaceCover") is True,
        "uses_unmixr_narration_audio": proof.get("usesUnmixrNarrationAudio") is True,
        "marker_media_not_used": proof.get("markerMediaUsed") is False,
        "synthetic_backup_audio_not_used": proof.get("syntheticBackupAudioUsed") is False,
        "raw_runtime_path_not_exposed": receipt.get("rawRuntimePathExposed") is False,
        "raw_provider_secret_not_exposed": receipt.get("rawProviderSecretExposed") is False,
    }
    failed = [key for key, passed in flags.items() if not passed]
    return {
        "id": "chummer_movie_story_scene_playback_verified",
        "label": "Chummer media story-scene movie is real, hash-bound, playable, and uses accepted story, selected face cover, and Unmixr audio",
        "status": "proved" if not failed else "blocked",
        "evidence": "dossier_video_import_receipt_and_live_import_hashes",
        "flags": flags,
        "failedFlags": failed,
        "receiptPath": receipt_path.as_posix(),
        "artifactPath": artifact_path.as_posix(),
        "receiptSha256": sha256_file(receipt_path) if receipt_path.is_file() else "",
        "artifactSha256": sha256_file(artifact_path) if artifact_path.is_file() else "",
        "videoUrlSha256": sha256_text(string(request.get("dossierVideoUrl"))) if string(request.get("dossierVideoUrl")) else "",
    }


def dossier_packaging_row(live_import_path: Path, branch: Path, request: dict[str, Any], live_evidence: dict[str, Any], context: OriginEditionContext) -> dict[str, Any]:
    book_receipt_path = (
        Path(string(request.get("bookArtifactReceiptPath")))
        if string(request.get("bookArtifactReceiptPath")).startswith("/")
        else live_import_path.parent / string(request.get("bookArtifactReceiptPath") or "book-artifact-import.receipt.json")
    )
    ebook_path = (
        Path(string(request.get("bookArtifactPath")))
        if string(request.get("bookArtifactPath")).startswith("/")
        else live_import_path.parent / string(request.get("bookArtifactPath"))
    )
    pdf_path = branch / "dossier/book.pdf"
    pdf_receipt_path = branch / "dossier/pdf-cover.receipt.json"
    book_receipt = read_json(book_receipt_path) if book_receipt_path.is_file() else {}
    pdf_receipt = read_json(pdf_receipt_path) if pdf_receipt_path.is_file() else {}
    book_tokens = tokens(book_receipt)
    pdf_tokens = tokens(pdf_receipt)
    project_id = string(request.get("projectId")) or context.project_id
    expected_book_url = origin_owner_url(context.base_url, project_id, "/book")
    flags = {
        "book_receipt_present": book_receipt_path.is_file(),
        "book_receipt_verified": is_pass(book_receipt),
        "ebook_artifact_present": ebook_path.is_file() and ebook_path.stat().st_size > 0,
        "pdf_artifact_present": pdf_path.is_file() and pdf_path.stat().st_size > 0,
        "pdf_receipt_present": pdf_receipt_path.is_file(),
        "pdf_receipt_verified": is_pass(pdf_receipt),
        "book_artifact_verified_in_import": request.get("bookArtifactVerified") is True,
        "book_url_is_chummer_book_route": string(request.get("bookArtifactUrl")) == expected_book_url,
        "ebook_sha_matches_import_evidence": contains_value(book_receipt.get("artifactSha256"), live_evidence.get("bookArtifactSha256")),
        "ebook_file_sha_matches_import_evidence": ebook_path.is_file() and sha256_file(ebook_path) == string(live_evidence.get("bookArtifactSha256")),
        "pdf_sha_matches_receipt": pdf_path.is_file() and sha256_file(pdf_path) == string(pdf_receipt.get("pdfSha256")),
        "accepted_manuscript_embedded": "accepted_humanized_manuscript_embedded" in book_tokens,
        "accepted_manuscript_sha_bound": string(live_evidence.get("acceptedHumanizedManuscriptSha256")) in book_tokens,
        "ebook_cover_embedded": "ebook_cover_embedded" in book_tokens,
        "pdf_cover_embedded": "pdf_cover_embedded" in book_tokens and "pdf_cover_embedded" in pdf_tokens,
        "pdf_cover_sha_matches_story_cover": string(pdf_receipt.get("coverSha256")) == string(live_evidence.get("storySceneCoverSha256")),
        "pdf_manuscript_sha_matches_accepted": string(pdf_receipt.get("manuscriptSha256")) == string(live_evidence.get("acceptedHumanizedManuscriptSha256")),
        "pdf_story_starts_without_preamble": pdf_receipt.get("storyStartsWithoutPreamble") is True and "story_starts_without_preamble" in pdf_tokens,
        "pdf_raw_runtime_paths_not_exposed": pdf_receipt.get("rawRuntimePathsExposed") is False,
    }
    failed = [key for key, passed in flags.items() if not passed]
    return {
        "id": "dossier_ebook_pdf_packaging_verified",
        "label": "Ebook and PDF dossier are hash-bound to accepted manuscript and rendered cover with no preamble",
        "status": "proved" if not failed else "blocked",
        "evidence": "book_artifact_import_and_pdf_materialization_receipts",
        "flags": flags,
        "failedFlags": failed,
        "bookReceiptPath": book_receipt_path.as_posix(),
        "pdfReceiptPath": pdf_receipt_path.as_posix(),
        "ebookPath": ebook_path.as_posix(),
        "pdfPath": pdf_path.as_posix(),
        "bookReceiptSha256": sha256_file(book_receipt_path) if book_receipt_path.is_file() else "",
        "pdfReceiptSha256": sha256_file(pdf_receipt_path) if pdf_receipt_path.is_file() else "",
        "bookUrlSha256": sha256_text(string(request.get("bookArtifactUrl"))) if string(request.get("bookArtifactUrl")) else "",
    }


def m4b_narration_row(live_import_path: Path, request: dict[str, Any], live_evidence: dict[str, Any]) -> dict[str, Any]:
    gate_path = (
        Path(string(request.get("m4bProviderImportReceiptPath")))
        if string(request.get("m4bProviderImportReceiptPath")).startswith("/")
        else live_import_path.parent / string(request.get("m4bProviderImportReceiptPath"))
    )
    m4b_path = (
        Path(string(request.get("audiobookPath")))
        if string(request.get("audiobookPath")).startswith("/")
        else live_import_path.parent / string(request.get("audiobookPath"))
    )
    gate = read_json(gate_path) if gate_path.is_file() else {}
    provider_path = (
        Path(string(gate.get("providerReceiptPath")))
        if string(gate.get("providerReceiptPath")).startswith("/")
        else live_import_path.parent / string(gate.get("providerReceiptPath"))
    )
    provider = read_json(provider_path) if provider_path.is_file() else {}
    gate_tokens = tokens(gate)
    provider_tokens = tokens(provider)
    expected_audio_sha = string(live_evidence.get("audiobookSha256"))
    expected_cover_sha = string(live_evidence.get("storySceneCoverSha256"))
    expected_manuscript_sha = string(live_evidence.get("acceptedHumanizedManuscriptSha256"))
    flags = {
        "gate_receipt_present": gate_path.is_file(),
        "provider_receipt_present": provider_path.is_file(),
        "gate_receipt_passed": is_pass(gate),
        "provider_receipt_verified": is_pass(provider),
        "provider_is_unmixr": string(provider.get("provider")).lower() == "unmixr" and string(provider.get("voiceProvider")).lower() == "unmixr",
        "audiobook_artifact_present": m4b_path.is_file() and m4b_path.stat().st_size > 0,
        "audiobook_file_sha_matches_import": m4b_path.is_file() and sha256_file(m4b_path) == expected_audio_sha,
        "gate_m4b_sha_matches_import": string(gate.get("m4bSha256")) == expected_audio_sha,
        "provider_m4b_sha_matches_import": string(provider.get("m4bSha256") or provider.get("audiobookSha256")) == expected_audio_sha,
        "gate_cover_sha_matches_story_cover": string(gate.get("coverSha256")) == expected_cover_sha,
        "provider_cover_sha_matches_story_cover": string(provider.get("coverSha256")) == expected_cover_sha,
        "gate_source_sha_matches_accepted_manuscript": string(gate.get("sourceSha256")) == expected_manuscript_sha,
        "provider_manuscript_sha_matches_accepted": string(provider.get("manuscriptSha256") or provider.get("sourceSha256")) == expected_manuscript_sha,
        "gate_links_provider_receipt_sha": provider_path.is_file() and string(gate.get("providerReceiptSha256")) == sha256_file(provider_path),
        "provider_direct_publish_disallowed": provider.get("directProviderPublishingAllowed") is False,
        "gate_raw_credentials_not_exposed": gate.get("rawCredentialExposed") is False and gate.get("rawProviderTokenExposed") is False,
        "provider_raw_credentials_not_exposed": provider.get("rawCredentialExposed") is False and provider.get("rawProviderTokenExposed") is False,
        "gate_raw_runtime_paths_not_exposed": gate.get("rawRuntimePathsExposed") is False,
        "tokens_bind_unmixr_and_cover_and_m4b": (
            "provider:Unmixr" in gate_tokens
            and "provider:Unmixr" in provider_tokens
            and expected_audio_sha in gate_tokens
            and f"m4b_sha256:{expected_audio_sha}" in provider_tokens
            and expected_cover_sha in gate_tokens
            and f"cover_sha256:{expected_cover_sha}" in provider_tokens
            and "m4b_cover_embedded" in gate_tokens
        ),
        "accepted_humanized_manuscript_token_present": (
            "accepted_humanized_manuscript" in gate_tokens
            and f"accepted_humanized_manuscript_sha256:{expected_manuscript_sha}" in provider_tokens
        ),
    }
    failed = [key for key, passed in flags.items() if not passed]
    return {
        "id": "m4b_unmixr_narration_import_verified",
        "label": "M4B audiobook uses verified Unmixr narration, accepted manuscript, embedded cover, and no provider/direct-publish leakage",
        "status": "proved" if not failed else "blocked",
        "evidence": "m4b_provider_gate_and_unmixr_provider_receipts",
        "flags": flags,
        "failedFlags": failed,
        "gateReceiptPath": gate_path.as_posix(),
        "providerReceiptPath": provider_path.as_posix(),
        "m4bPath": m4b_path.as_posix(),
        "gateReceiptSha256": sha256_file(gate_path) if gate_path.is_file() else "",
        "providerReceiptSha256": sha256_file(provider_path) if provider_path.is_file() else "",
        "m4bSha256": sha256_file(m4b_path) if m4b_path.is_file() else "",
    }


def local_authenticated_route_row(path: Path, request: dict[str, Any], context: OriginEditionContext) -> dict[str, Any]:
    project_id = string(request.get("projectId")) or context.project_id
    flags = {
        "receipt_present": path.is_file(),
        "receipt_passed": False,
        "local_authenticated_instance": False,
        "not_deployed_route_claim": False,
        "no_local_fixture_artifacts": False,
        "raw_credentials_not_exposed": False,
        "owner_detail_status_ok": False,
        "owner_library_status_ok": False,
        "anonymous_detail_redirect_verified": False,
        "anonymous_artifact_redirect_verified": False,
        "logged_in_browser_verified": False,
        "selected_face_cover_visible": False,
        "read_tab_visible": False,
        "listen_tab_visible": False,
        "watch_tab_visible": False,
        "canon_audit_tab_visible": False,
        "read_gate_verified": False,
        "listen_gate_verified": False,
        "watch_gate_verified": False,
        "cover_route_verified": False,
        "book_route_verified": False,
        "live_provider_artifacts_verified": False,
        "live_provider_delivery_verified": False,
        "local_route_urls_are_private_origin_routes": False,
        "url_hashes_match_expected_local_routes": False,
        "required_tokens_present": False,
    }
    row: dict[str, Any] = {
        "id": "local_authenticated_route_tabs_verified",
        "label": "Local authenticated Chummer route exposes Read, Listen, Watch, Canon Audit, cover, book, and private access gates",
        "path": path.as_posix(),
        "flags": flags,
    }
    if not path.is_file():
        row["status"] = "missing"
        row["evidence"] = "receipt_missing"
        row["failedFlags"] = [key for key, passed in flags.items() if not passed]
        return row
    payload = read_json(path)
    route_hashes = payload.get("urlHashes") if isinstance(payload.get("urlHashes"), dict) else {}
    payload_tokens = tokens(payload)
    expected = {
        "owner": string(payload.get("owner_detail_page")),
        "read": string(payload.get("read_url")),
        "listen": string(payload.get("listen_url")),
        "video": string(payload.get("watch_url")),
        "cover": string(payload.get("selected_face_cover_url")),
        "book": string(payload.get("book_url")),
    }
    expected_paths = {
        "owner": f"/account/work/origin-dossiers/{project_id}",
        "read": f"/account/work/origin-dossiers/{project_id}/read",
        "listen": f"/account/work/origin-dossiers/{project_id}/listen",
        "video": f"/account/work/origin-dossiers/{project_id}/video",
        "cover": f"/account/work/origin-dossiers/{project_id}/cover",
        "book": f"/account/work/origin-dossiers/{project_id}/book",
    }
    flags["receipt_passed"] = is_pass(payload)
    flags["local_authenticated_instance"] = payload.get("localAuthenticatedRunSiteInstance") is True
    flags["not_deployed_route_claim"] = payload.get("deployedRouteClaimAllowed") is False
    flags["no_local_fixture_artifacts"] = payload.get("local_fixture_artifacts") is False
    flags["raw_credentials_not_exposed"] = payload.get("rawCredentialExposed") is False and payload.get("rawSessionTokenExposed") is False
    flags["owner_detail_status_ok"] = payload.get("ownerDetailStatus") == 200
    flags["owner_library_status_ok"] = payload.get("ownerLibraryStatus") == 200
    flags["anonymous_detail_redirect_verified"] = payload.get("anonymousDetailRedirectVerified") is True
    flags["anonymous_artifact_redirect_verified"] = payload.get("anonymousArtifactRedirectVerified") is True
    flags["logged_in_browser_verified"] = payload.get("logged_in_browser_verified") is True
    flags["selected_face_cover_visible"] = payload.get("selected_face_cover_visible") is True
    flags["read_tab_visible"] = payload.get("read_tab_visible") is True
    flags["listen_tab_visible"] = payload.get("listen_tab_visible") is True
    flags["watch_tab_visible"] = payload.get("watch_tab_visible") is True
    flags["canon_audit_tab_visible"] = payload.get("canon_audit_tab_visible") is True
    flags["read_gate_verified"] = payload.get("read_gate_verified") is True
    flags["listen_gate_verified"] = payload.get("chummer_run_listen_gate_verified") is True
    flags["watch_gate_verified"] = payload.get("watch_gate_verified") is True
    flags["cover_route_verified"] = payload.get("coverRouteVerified") is True
    flags["book_route_verified"] = payload.get("bookRouteVerified") is True
    flags["live_provider_artifacts_verified"] = payload.get("live_provider_artifacts_verified") is True
    flags["live_provider_delivery_verified"] = payload.get("live_provider_delivery_verified") is True
    flags["local_route_urls_are_private_origin_routes"] = all(
        string(url)
        and urlparse(url).scheme in {"http", "https"}
        and urlparse(url).path == expected_paths[key]
        for key, url in expected.items()
    )
    flags["url_hashes_match_expected_local_routes"] = flags["local_route_urls_are_private_origin_routes"] and all(
        string(route_hashes.get(key)) == sha256_text(url)
        for key, url in expected.items()
    )
    flags["required_tokens_present"] = all(token in payload_tokens for token in (
        "authenticated_chummer_run_route_proof",
        "read_tab_visible",
        "listen_tab_visible",
        "watch_tab_visible",
        "canon_audit_tab_visible",
        "anonymous_private_access_redirects_to_login",
        "owner_read_listen_watch_routes_verified",
    ))
    failed = [key for key, passed in flags.items() if not passed]
    row.update(
        {
            "status": "proved" if not failed else "blocked",
            "evidence": "authenticated_chummer_route_receipt_strict_tab_and_gate_matrix",
            "failedFlags": failed,
            "sha256": sha256_file(path),
            "localRouteUrlHashes": {key: sha256_text(url) for key, url in expected.items()},
        }
    )
    return row


def materialize(evidence_root: Path, output: Path, context: OriginEditionContext | None = None) -> dict[str, Any]:
    evidence_root = evidence_root.resolve()
    live_import_path = evidence_root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    live_import = read_json(live_import_path) if live_import_path.is_file() else {}
    request = live_import.get("importRequest") if isinstance(live_import.get("importRequest"), dict) else {}
    live_evidence = live_import.get("evidence") if isinstance(live_import.get("evidence"), dict) else {}
    context = context or OriginEditionContext.from_env(
        project_id=string(request.get("projectId")),
        namespace=string(request.get("originEditionNamespace")),
    )
    namespace = context.resolved_namespace
    branch = evidence_root / namespace

    deployed_probe_path = branch / "deployed-chummer-browser-probe.receipt.json"
    deployed_probe = read_json(deployed_probe_path) if deployed_probe_path.is_file() else {}
    gold_audit_path = evidence_root / "ORIGIN_EDITION_GOLD_CURRENT_GAP_AUDIT.generated.json"
    gold_audit = read_json(gold_audit_path) if gold_audit_path.is_file() else {}

    rows: list[dict[str, Any]] = [
        receipt_row("approved_canon_packet_receipt", "Approved sample runner canon/source packet receipt", evidence_root / "source-packet-approval.receipt.json"),
        bool_row("approved_canon_packet_file", "Approved sample runner canon packet file exists", artifact_exists(live_import_path, request.get("sourcePacketPath")), string(request.get("sourcePacketPath"))),
        canon_authority_row(evidence_root / "source-packet-approval.receipt.json", evidence_root / "canon-privacy-audit.receipt.json"),
        source_packet_integrity_row(live_import_path, request, live_evidence),
        receipt_row("story_generation_receipt", "Provider/story manuscript import receipt", evidence_root / "provider-manuscript-import.receipt.json"),
        bool_row("provider_manuscript_file", "Provider manuscript file exists", artifact_exists(live_import_path, request.get("providerManuscriptPath")), string(request.get("providerManuscriptPath"))),
        receipt_row("undetectable_humanizer_receipt", "Undetectable Humanizer post-step receipt", evidence_root / "undetectable-humanizer.receipt.json"),
        receipt_row("humanizer_quality_receipt", "Undetectable Humanizer quality gate receipt", evidence_root / "undetectable-humanizer-quality-gate.browseract.normalized.receipt.json"),
        receipt_row("canon_privacy_audit", "Canon/privacy audit receipt", evidence_root / "canon-privacy-audit.receipt.json"),
        receipt_row("cover_generation_receipt", "Rendered story-scene cover generation receipt", evidence_root / "story-scene-cover.receipt.json"),
        receipt_row("cover_consistency_receipt", "Cover consistency proof", branch / "cover-consistency-strict.receipt.json"),
        cover_surface_row(branch / "cover-consistency-strict.receipt.json"),
        receipt_row("ebook_import_receipt", "Ebook/PDF packaging and import receipt", evidence_root / "book-artifact-import.receipt.json"),
        bool_row("ebook_artifact_file", "Ebook artifact exists", artifact_exists(live_import_path, request.get("bookArtifactPath")), string(request.get("bookArtifactPath"))),
        bool_row("ebook_artifact_namespace", "Ebook artifact is under Origin dossier branch", path_under(request.get("bookArtifactPath"), f"{namespace}/dossier", suffixes=(".epub",)), string(request.get("bookArtifactPath"))),
        dossier_packaging_row(live_import_path, branch, request, live_evidence, context),
        receipt_row("m4b_provider_receipt", "M4B provider narration/import receipt", Path(string(request.get("m4bProviderImportReceiptPath"))) if string(request.get("m4bProviderImportReceiptPath")).startswith("/") else live_import_path.parent / string(request.get("m4bProviderImportReceiptPath"))),
        bool_row("m4b_provider_receipt_namespace", "M4B provider receipt is under Origin audiobook branch", path_under(request.get("m4bProviderImportReceiptPath"), f"{namespace}/audiobook", suffixes=(".json",)), string(request.get("m4bProviderImportReceiptPath"))),
        bool_row("m4b_artifact_file", "M4B audiobook artifact exists", artifact_exists(live_import_path, request.get("audiobookPath")), string(request.get("audiobookPath"))),
        bool_row("m4b_artifact_namespace", "M4B audiobook artifact is under Origin audiobook branch", path_under(request.get("audiobookPath"), f"{namespace}/audiobook", suffixes=(".m4b",)), string(request.get("audiobookPath"))),
        m4b_narration_row(live_import_path, request, live_evidence),
        receipt_row("audiobookshelf_import_receipt", "Audiobookshelf import/share receipt", Path(string(request.get("audiobookshelfImportReceiptPath"))) if string(request.get("audiobookshelfImportReceiptPath")).startswith("/") else live_import_path.parent / string(request.get("audiobookshelfImportReceiptPath"))),
        bool_row("audiobookshelf_import_receipt_namespace", "Audiobookshelf import/share receipt is under Origin audiobook branch", path_under(request.get("audiobookshelfImportReceiptPath"), f"{namespace}/audiobook", suffixes=(".json",)), string(request.get("audiobookshelfImportReceiptPath"))),
        audiobookshelf_share_row(evidence_root, branch, request),
        receipt_row("movie_generation_receipt", "Movie generation/import/playback receipt", Path(string(request.get("dossierVideoReceiptPath"))) if string(request.get("dossierVideoReceiptPath")).startswith("/") else live_import_path.parent / string(request.get("dossierVideoReceiptPath"))),
        bool_row("movie_generation_receipt_namespace", "Movie generation receipt is under Origin movie branch", path_under(request.get("dossierVideoReceiptPath"), f"{namespace}/movie", suffixes=(".json",)), string(request.get("dossierVideoReceiptPath"))),
        bool_row("movie_artifact_file", "Story scene movie artifact exists", artifact_exists(live_import_path, request.get("dossierVideoPath")), string(request.get("dossierVideoPath"))),
        bool_row("movie_artifact_namespace", "Story scene movie artifact is under Origin movie branch", path_under(request.get("dossierVideoPath"), f"{namespace}/movie", suffixes=(".mp4",)), string(request.get("dossierVideoPath"))),
        movie_playback_row(live_import_path, request, live_evidence, context),
        receipt_row("local_authenticated_chummer_route", "Local authenticated Chummer route proof", branch / "authenticated-chummer-route-live.receipt.json"),
        local_authenticated_route_row(branch / "authenticated-chummer-route-live.receipt.json", request, context),
        receipt_row("runsite_integration_proof", "RunSite integration proof", branch / "runsite-integration-proof.receipt.json"),
        runsite_handoff_row(branch / "runsite-integration-proof.receipt.json"),
        receipt_row("telegram_delivery_receipt", "Telegram read/listen/watch/open link delivery receipt", Path(string(request.get("telegramShareDeliveryReceiptPath"))) if string(request.get("telegramShareDeliveryReceiptPath")).startswith("/") else live_import_path.parent / string(request.get("telegramShareDeliveryReceiptPath"))),
        telegram_link_bundle_row(branch / "telegram-origin-link-bundle-live.receipt.json", string(request.get("projectId")) or context.project_id, context.base_url),
        receipt_row("final_no_fallback_no_sentinel_audit", "Final no-fallback/no-sentinel audit", Path(string(request.get("finalNoFallbackNoSentinelAuditReceiptPath"))) if string(request.get("finalNoFallbackNoSentinelAuditReceiptPath")).startswith("/") else live_import_path.parent / string(request.get("finalNoFallbackNoSentinelAuditReceiptPath"))),
        final_bundle_row(Path(string(request.get("finalNoFallbackNoSentinelAuditReceiptPath"))) if string(request.get("finalNoFallbackNoSentinelAuditReceiptPath")).startswith("/") else live_import_path.parent / string(request.get("finalNoFallbackNoSentinelAuditReceiptPath"))),
        secret_hygiene_row(evidence_root),
        provider_publish_boundary_row(evidence_root, live_import, request),
        receipt_row("deployed_operator_handoff", "Secret-safe deployed operator handoff", branch / "deployed-operator-handoff.receipt.json", pass_status_required=False),
        receipt_row("current_gold_gap_audit", "Current gold gap audit", gold_audit_path, pass_status_required=False),
    ]

    deployed_flags = {
        "logged_in_browser_verified": deployed_probe.get("logged_in_browser_verified") is True,
        "selected_face_cover_visible": deployed_probe.get("selected_face_cover_visible") is True,
        "read_tab_visible": deployed_probe.get("read_tab_visible") is True,
        "listen_tab_visible": deployed_probe.get("listen_tab_visible") is True,
        "watch_tab_visible": deployed_probe.get("watch_tab_visible") is True,
        "canon_audit_tab_visible": deployed_probe.get("canon_audit_tab_visible") is True,
        "read_gate_verified": deployed_probe.get("read_gate_verified") is True,
        "listen_gate_verified": deployed_probe.get("chummer_run_listen_gate_verified") is True,
        "watch_gate_verified": deployed_probe.get("watch_gate_verified") is True,
        "audiobook_share_url_trusted": deployed_probe.get("audiobook_share_url_trusted") is True,
        "dossier_share_url_trusted": deployed_probe.get("dossier_share_url_trusted") is True,
        "unauthenticated_detail_redirect_verified": deployed_probe.get("unauthenticated_detail_redirect_verified") is True,
        "unauthenticated_read_redirect_verified": deployed_probe.get("unauthenticated_read_redirect_verified") is True,
        "unauthenticated_listen_redirect_verified": deployed_probe.get("unauthenticated_listen_redirect_verified") is True,
        "unauthenticated_book_redirect_verified": deployed_probe.get("unauthenticated_book_redirect_verified") is True,
        "unauthenticated_cover_redirect_verified": deployed_probe.get("unauthenticated_cover_redirect_verified") is True,
        "unauthenticated_video_redirect_verified": deployed_probe.get("unauthenticated_video_redirect_verified") is True,
        "all_private_routes_login_protected": deployed_probe.get("all_private_routes_login_protected") is True,
        "owner_playback_e2e_verified": deployed_probe.get("owner_playback_e2e_verified") is True,
    }
    rows.append(
        {
            "id": "deployed_user_login_read_listen_watch",
            "label": "User can log into deployed Chummer and read/listen/watch/canon-audit",
            "status": "proved" if all(deployed_flags.values()) and string(deployed_probe.get("status")) == "pass" else "blocked",
            "evidence": "deployed_browser_probe",
            "sha256": sha256_file(deployed_probe_path) if deployed_probe_path.is_file() else "",
            "flags": deployed_flags,
            "blockers": deployed_probe.get("blockers", []),
        }
    )

    hard_gates = {
        "published_for_owner": string(request.get("publicationState")) == "published_for_owner",
        "approved_sources_only": request.get("missingGoldRequirements") == [] and is_pass(live_import),
        "source_packet_integrity_and_consent_verified": next((row for row in rows if row.get("id") == "source_packet_integrity_and_consent_verified"), {}).get("status") == "proved",
        "no_provider_direct_publish": next((row for row in rows if row.get("id") == "provider_publish_boundary_verified"), {}).get("status") == "proved",
        "no_fallback_audio": is_pass(read_json(Path(string(request.get("finalNoFallbackNoSentinelAuditReceiptPath"))) if string(request.get("finalNoFallbackNoSentinelAuditReceiptPath")).startswith("/") else live_import_path.parent / string(request.get("finalNoFallbackNoSentinelAuditReceiptPath")))),
        "same_cover_sha_bound": bool(live_evidence.get("storySceneCoverSha256")),
        "dossier_ebook_pdf_packaging_verified": next((row for row in rows if row.get("id") == "dossier_ebook_pdf_packaging_verified"), {}).get("status") == "proved",
        "m4b_unmixr_narration_import_verified": next((row for row in rows if row.get("id") == "m4b_unmixr_narration_import_verified"), {}).get("status") == "proved",
        "audiobookshelf_dossier_and_audiobook_shared": next((row for row in rows if row.get("id") == "audiobookshelf_dossier_and_audiobook_share_verified"), {}).get("status") == "proved",
        "chummer_movie_story_scene_playback_verified": next((row for row in rows if row.get("id") == "chummer_movie_story_scene_playback_verified"), {}).get("status") == "proved",
        "local_authenticated_route_tabs_verified": next((row for row in rows if row.get("id") == "local_authenticated_route_tabs_verified"), {}).get("status") == "proved",
        "runsite_handoff_constraints_verified": next((row for row in rows if row.get("id") == "runsite_handoff_constraints_verified"), {}).get("status") == "proved",
        "no_committed_or_receipt_secrets_claimed": next((row for row in rows if row.get("id") == "secret_hygiene_verified"), {}).get("status") == "proved",
        "gold_audit_completion_claim_allowed": gold_audit.get("goalCompletionClaimAllowed") is True,
    }

    blocked_rows = [row["id"] for row in rows if row.get("status") != "proved"]
    blocked_gates = [key for key, value in hard_gates.items() if not value]
    status = "pass" if not blocked_rows and not blocked_gates else "blocked"
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "status": status,
        "finalVerdict": "ORIGIN_EDITION_GOLD_READY" if status == "pass" else "ORIGIN_EDITION_GOLD_BLOCKED",
        "goalCompletionClaimAllowed": status == "pass",
        "namespace": namespace,
        "projectId": string(request.get("projectId")) or context.project_id,
        "chummerRunOwnerUrl": live_import.get("chummerRunOwnerUrl"),
        "blockedRows": blocked_rows,
        "hardGates": hard_gates,
        "blockedHardGates": blocked_gates,
        "rows": rows,
        "privacy": {
            "rawCredentialExposed": False,
            "rawSessionTokenExposed": False,
            "envValuesExposed": False,
            "deploymentPerformed": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Origin Edition Gold E2E requirement completion matrix.")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output or args.evidence_root / "ORIGIN_EDITION_GOLD_COMPLETION_MATRIX.generated.json"
    payload = materialize(args.evidence_root, output)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
