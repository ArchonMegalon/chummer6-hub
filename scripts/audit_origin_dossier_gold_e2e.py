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
from origin_edition_provider_config import is_trusted_audiobookshelf_share, origin_owner_url


CONTRACT_NAME = "chummer.origin_dossier_gold_e2e_audit.v1"
LIVE_IMPORT_CONTRACT_NAME = "chummer.origin_dossier_live_artifact_import_request.v1"
EA_LIVE_DELIVERY_CONTRACT_NAME = "ea.telegram_audiobook_live_delivery_receipt.v1"
EA_READINESS_CONTRACT_NAME = "ea.telegram_audiobook_live_readiness_checklist.v1"
DEPLOYED_OPERATOR_HANDOFF_CONTRACT_NAME = "chummer.origin_edition.deployed_operator_handoff.v1"
DEFAULT_OUTPUT_NAME = "ORIGIN_DOSSIER_GOLD_E2E_AUDIT.generated.json"
REQUIRED_IMPORT_FLAGS = (
    "providerAuthoredManuscriptImported",
    "undetectableHumanizerApplied",
    "bookArtifactVerified",
    "dossierVideoVerified",
    "storySceneCoverUsesSelectedCharacterFace",
    "audiobookshelfPlaybackVerified",
    "telegramShareDelivered",
)
REQUIRED_BROWSER_FLAGS = (
    "logged_in_browser_verified",
    "selected_face_cover_visible",
    "read_tab_visible",
    "listen_tab_visible",
    "watch_tab_visible",
    "canon_audit_tab_visible",
    "read_gate_verified",
    "chummer_run_listen_gate_verified",
    "watch_gate_verified",
    "unauthenticated_detail_redirect_verified",
    "unauthenticated_read_redirect_verified",
    "unauthenticated_listen_redirect_verified",
    "unauthenticated_book_redirect_verified",
    "unauthenticated_cover_redirect_verified",
    "unauthenticated_video_redirect_verified",
    "all_private_routes_login_protected",
    "live_provider_artifacts_verified",
    "live_provider_delivery_verified",
    "owner_playback_e2e_verified",
)
RAW_LEAK_MARKERS = (
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
FAKE_MARKERS = (
    "stub",
    "fallback",
    "placeholder",
    "self_generated",
    "self-generated",
    "local_fixture",
    "browser proof",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _string(value: object) -> str:
    return str(value or "").strip()


def _bool(value: object) -> bool:
    return value is True or _string(value).lower() in {"1", "true", "yes", "pass", "verified"}


def _is_sha256(value: object) -> bool:
    text = _string(value)
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text.lower())


def _contains_marker(value: object, markers: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        lowered = (
            value.lower()
            .replace("no-fallback", "")
            .replace("no_fallback", "")
            .replace("nofallback", "")
            .replace("no fallback", "")
        )
        return any(marker.lower() in lowered for marker in markers)
    if isinstance(value, dict):
        return any(_contains_marker(item, markers) for item in value.values())
    if isinstance(value, list):
        return any(_contains_marker(item, markers) for item in value)
    return False


def _trusted_audiobookshelf_share(url: str) -> bool:
    return is_trusted_audiobookshelf_share(url)


def _chummer_owner_url(url: str, project_id: str, suffix: str = "", *, base_url: str = "https://chummer.run") -> bool:
    parsed = urlparse(url)
    expected = urlparse(origin_owner_url(base_url, project_id, suffix))
    return parsed.scheme.lower() == expected.scheme.lower() and parsed.hostname == expected.hostname and parsed.path == expected.path


def _add_issue(issues: list[str], condition: bool, code: str) -> None:
    if not condition:
        issues.append(code)


def _audit_live_import(path: Path) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    payload = _read_json(path)
    request = payload.get("importRequest") if isinstance(payload.get("importRequest"), dict) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    project_id = _string(request.get("projectId") or payload.get("projectId"))
    share_url = _string(request.get("audiobookshelfShareUrl") or payload.get("audiobookshelfShareUrl"))
    owner_url = _string(payload.get("chummerRunOwnerUrl"))
    parsed_owner = urlparse(owner_url)
    base_url = f"{parsed_owner.scheme}://{parsed_owner.netloc}" if parsed_owner.scheme and parsed_owner.netloc else "https://chummer.run"

    _add_issue(issues, _string(payload.get("contractName")) == LIVE_IMPORT_CONTRACT_NAME, "live_import_contract_mismatch")
    _add_issue(issues, _string(payload.get("status")) == "pass", "live_import_not_pass")
    _add_issue(issues, bool(project_id), "project_id_missing")
    _add_issue(issues, _string(request.get("publicationState")) == "published_for_owner", "import_publication_state_not_published_for_owner")
    for flag in REQUIRED_IMPORT_FLAGS:
        _add_issue(issues, request.get(flag) is True, f"import_flag_missing:{flag}")
    _add_issue(issues, request.get("missingGoldRequirements") == [], "import_missing_gold_requirements_present")
    _add_issue(issues, _trusted_audiobookshelf_share(share_url), "untrusted_audiobookshelf_share")
    if project_id:
        _add_issue(issues, _chummer_owner_url(owner_url, project_id, base_url=base_url), "owner_url_not_chummer_run")
        _add_issue(issues, _chummer_owner_url(_string(request.get("bookArtifactUrl")), project_id, "/book", base_url=base_url), "book_url_not_chummer_run")
        _add_issue(issues, _chummer_owner_url(_string(request.get("storySceneCoverUrl")), project_id, "/cover", base_url=base_url), "cover_url_not_chummer_run")
        _add_issue(issues, _chummer_owner_url(_string(request.get("dossierVideoUrl")), project_id, "/video", base_url=base_url), "video_url_not_chummer_run")
    for key in (
        "sourcePacketSha256",
        "providerManuscriptSha256",
        "humanizerQualityReceiptSha256",
        "bookArtifactSha256",
        "storySceneCoverSha256",
        "audiobookSha256",
        "dossierVideoSha256",
        "eaAudiobookJobReceiptSha256",
        "eaM4bProviderImportReceiptSha256",
        "eaTelegramLiveDeliveryReceiptSha256",
    ):
        _add_issue(issues, _is_sha256(evidence.get(key)), f"live_import_evidence_hash_missing:{key}")
    for key in (
        "sourcePacketPath",
        "sourcePacketReceiptPath",
        "canonAuditReceiptPath",
        "providerManuscriptPath",
        "providerManuscriptReceiptPath",
        "humanizerReceiptPath",
        "humanizerQualityReceiptPath",
        "bookArtifactPath",
        "bookArtifactReceiptPath",
        "storySceneCoverPath",
        "storySceneCoverReceiptPath",
        "audiobookPath",
        "m4bProviderImportReceiptPath",
        "audiobookshelfImportReceiptPath",
        "dossierVideoPath",
        "dossierVideoReceiptPath",
        "telegramShareDeliveryReceiptPath",
    ):
        value = _string(request.get(key))
        artifact_path = Path(value) if value else Path()
        if value and not artifact_path.is_absolute():
            artifact_path = path.parent / artifact_path
        _add_issue(issues, bool(value) and artifact_path.is_file(), f"import_artifact_missing:{key}")
    _add_issue(issues, not _contains_marker(payload, RAW_LEAK_MARKERS), "live_import_raw_secret_or_path_leak")
    _add_issue(issues, not _contains_marker(payload, FAKE_MARKERS), "live_import_fake_or_fallback_marker")
    return {
        "project_id": project_id,
        "base_url": base_url,
        "audiobookshelf_share_url": share_url,
        "path": path.as_posix(),
        "sha256": _sha256_file(path),
    }, issues


def _audit_ea_delivery(path: Path, share_url: str, project_id: str, base_url: str) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    payload = _read_json(path)
    selected = payload.get("selected_delivery") if isinstance(payload.get("selected_delivery"), dict) else {}
    parsed_share = urlparse(share_url)
    _add_issue(issues, _string(payload.get("contract_name")) == EA_LIVE_DELIVERY_CONTRACT_NAME, "ea_delivery_contract_mismatch")
    _add_issue(issues, _string(payload.get("status")) == "pass", "ea_delivery_not_pass")
    _add_issue(issues, payload.get("live_delivery_claim_allowed") is True, "ea_live_delivery_claim_not_allowed")
    _add_issue(issues, payload.get("machine_playback_e2e_verified") is True, "ea_machine_playback_not_verified")
    _add_issue(issues, payload.get("failed_codes") in ([], None), "ea_delivery_failed_codes_present")
    _add_issue(issues, selected.get("public_share_url_present") is True, "ea_delivery_public_share_missing")
    _add_issue(issues, _string(selected.get("public_share_host")) == (parsed_share.hostname or ""), "ea_delivery_share_host_mismatch")
    _add_issue(issues, _string(selected.get("telegram_delivery_status")) == "sent", "ea_telegram_delivery_not_sent")
    _add_issue(issues, selected.get("telegram_delivery_message_id_present") is True, "ea_telegram_message_proof_missing")
    link_bundle = selected.get("origin_edition_link_bundle") if isinstance(selected.get("origin_edition_link_bundle"), dict) else {}
    _add_issue(issues, _string(link_bundle.get("status")) in {"sent", "pass", "delivered"}, "ea_origin_link_bundle_not_sent")
    _add_issue(issues, _string(link_bundle.get("project_id")) == project_id, "ea_origin_link_bundle_project_mismatch")
    _add_issue(issues, _string(link_bundle.get("telegram_delivery_status")) == "sent", "ea_origin_link_bundle_telegram_not_sent")
    _add_issue(issues, link_bundle.get("telegram_message_id_present") is True, "ea_origin_link_bundle_message_proof_missing")
    _add_issue(issues, link_bundle.get("all_required_links_present") is True, "ea_origin_link_bundle_missing_required_links")
    _add_issue(issues, link_bundle.get("raw_urls_exposed") is not True, "ea_origin_link_bundle_raw_urls_exposed")
    for key, expected_url in {
        "read_url_sha256": origin_owner_url(base_url, project_id, "/read"),
        "listen_url_sha256": origin_owner_url(base_url, project_id, "/listen"),
        "watch_url_sha256": origin_owner_url(base_url, project_id, "/video"),
        "open_in_chummer_url_sha256": origin_owner_url(base_url, project_id),
    }.items():
        _add_issue(issues, _string(link_bundle.get(key)) == _sha256_text(expected_url), f"ea_origin_link_bundle_hash_mismatch:{key}")
    _add_issue(issues, not _contains_marker(payload, RAW_LEAK_MARKERS), "ea_delivery_raw_secret_or_path_leak")
    return {
        "path": path.as_posix(),
        "sha256": _sha256_file(path),
        "real_user_playback_acceptance_verified": payload.get("real_user_playback_acceptance_verified") is True,
    }, issues


def _audit_browser_proof(path: Path, project_id: str, share_url: str, base_url: str) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    payload = _read_json(path)
    is_deployed_probe = _string(payload.get("contractName")) == "chummer.origin_edition.deployed_browser_probe.v1"
    _add_issue(issues, _string(payload.get("status")) == "pass", "browser_proof_not_pass")
    if is_deployed_probe and _string(payload.get("status")) != "pass":
        blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
        for blocker in blockers:
            code = _string(blocker)
            if code:
                issues.append(f"browser_deployed_probe_blocked:{code}")
    _add_issue(issues, _string(payload.get("project_id")) == project_id, "browser_project_id_mismatch")
    _add_issue(issues, payload.get("local_fixture_artifacts") is False, "browser_proof_is_local_fixture")
    if is_deployed_probe:
        _add_issue(issues, payload.get("deployedRouteClaimAllowed") is True, "browser_deployed_route_claim_not_allowed")
    for flag in REQUIRED_BROWSER_FLAGS:
        _add_issue(issues, payload.get(flag) is True, f"browser_flag_missing:{flag}")
    _add_issue(issues, _string(payload.get("base_url")).rstrip("/") == base_url.rstrip("/"), "browser_base_url_not_deployed_chummer_run")
    _add_issue(issues, _chummer_owner_url(_string(payload.get("owner_detail_page")), project_id, base_url=base_url), "browser_owner_detail_not_chummer_run")
    _add_issue(issues, _chummer_owner_url(_string(payload.get("selected_face_cover_url")), project_id, "/cover", base_url=base_url), "browser_cover_url_not_chummer_run")
    _add_issue(issues, _chummer_owner_url(_string(payload.get("read_url")), project_id, "/read", base_url=base_url), "browser_read_url_not_chummer_run")
    _add_issue(issues, _chummer_owner_url(_string(payload.get("book_url")), project_id, "/book", base_url=base_url), "browser_book_url_not_chummer_run")
    _add_issue(issues, _chummer_owner_url(_string(payload.get("listen_url")), project_id, "/listen", base_url=base_url), "browser_listen_url_not_chummer_run")
    _add_issue(issues, _chummer_owner_url(_string(payload.get("watch_url")), project_id, "/video", base_url=base_url), "browser_watch_url_not_chummer_run")
    _add_issue(issues, _string(payload.get("audiobookshelf_redirect")) == share_url, "browser_audiobookshelf_redirect_mismatch")
    _add_issue(issues, _trusted_audiobookshelf_share(_string(payload.get("audiobookshelf_redirect"))), "browser_audiobookshelf_redirect_untrusted")
    _add_issue(issues, not _contains_marker(payload, FAKE_MARKERS), "browser_fake_or_fallback_marker")
    return {
        "path": path.as_posix(),
        "sha256": _sha256_file(path),
        "contract_name": payload.get("contractName"),
        "deployed_route_claim_allowed": payload.get("deployedRouteClaimAllowed"),
        "blockers": payload.get("blockers", []),
        "owner_playback_e2e_verified": payload.get("owner_playback_e2e_verified") is True,
    }, issues


def _audit_readiness(path: Path | None) -> tuple[dict[str, Any], list[str]]:
    if path is None:
        return {}, []
    issues: list[str] = []
    payload = _read_json(path)
    _add_issue(issues, _string(payload.get("contract_name")) == EA_READINESS_CONTRACT_NAME, "ea_readiness_contract_mismatch")
    _add_issue(issues, _string(payload.get("status")) == "ready_for_live_epub_delivery_test", "ea_readiness_not_ready")
    _add_issue(issues, payload.get("can_run_live_epub_delivery_test") is True, "ea_readiness_live_delivery_test_not_allowed")
    _add_issue(issues, payload.get("public_share_delivery_prereqs_ready") is True, "ea_readiness_public_share_prereqs_not_ready")
    _add_issue(issues, payload.get("voice_sample_prereqs_ready") is True, "ea_readiness_voice_sample_prereqs_not_ready")
    _add_issue(issues, payload.get("delivery_blockers") == [], "ea_readiness_delivery_blockers_present")
    _add_issue(issues, payload.get("sample_blockers") == [], "ea_readiness_sample_blockers_present")
    privacy = payload.get("privacy") if isinstance(payload.get("privacy"), dict) else {}
    _add_issue(issues, privacy.get("env_values_exposed") is False, "ea_readiness_env_values_exposed")
    _add_issue(issues, privacy.get("raw_provider_voice_ids_exposed") is False, "ea_readiness_raw_provider_voice_ids_exposed")
    _add_issue(issues, privacy.get("raw_public_share_url_included") is False, "ea_readiness_raw_public_share_url_included")
    _add_issue(issues, privacy.get("raw_storage_paths_included") is False, "ea_readiness_raw_storage_paths_included")
    _add_issue(issues, privacy.get("raw_telegram_chat_id_included") is False, "ea_readiness_raw_telegram_chat_id_included")
    return {"path": path.as_posix(), "sha256": _sha256_file(path)}, issues


def _audit_deployed_operator_handoff(path: Path | None) -> tuple[dict[str, Any], list[str]]:
    if path is None:
        return {}, []
    issues: list[str] = []
    payload = _read_json(path)
    privacy = payload.get("privacy") if isinstance(payload.get("privacy"), dict) else {}
    _add_issue(issues, _string(payload.get("contractName")) == DEPLOYED_OPERATOR_HANDOFF_CONTRACT_NAME, "deployed_operator_handoff_contract_mismatch")
    _add_issue(issues, payload.get("goalCompletionClaimAllowed") is not True, "deployed_operator_handoff_must_not_claim_gold")
    _add_issue(issues, privacy.get("rawCredentialExposed") is False, "deployed_operator_handoff_raw_credential_exposed")
    _add_issue(issues, privacy.get("rawSessionTokenExposed") is False, "deployed_operator_handoff_raw_session_token_exposed")
    _add_issue(issues, privacy.get("envValuesExposed") is False, "deployed_operator_handoff_env_values_exposed")
    _add_issue(issues, privacy.get("deploymentPerformed") is False, "deployed_operator_handoff_deployment_performed")
    _add_issue(issues, not _contains_marker(payload, RAW_LEAK_MARKERS), "deployed_operator_handoff_raw_secret_or_path_leak")
    return {
        "path": path.as_posix(),
        "sha256": _sha256_file(path),
        "status": payload.get("status"),
        "gold_eligible": payload.get("goldEligible"),
        "goal_completion_claim_allowed": payload.get("goalCompletionClaimAllowed"),
        "blockers": payload.get("blockers", []),
        "required_env_present": (
            payload.get("requiredEnv", {})
            .get("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", {})
            .get("presentInCurrentProcess")
            if isinstance(payload.get("requiredEnv"), dict)
            else None
        ),
    }, issues


def audit(
    *,
    live_import_request: Path,
    ea_delivery_receipt: Path,
    browser_proof: Path,
    ea_readiness_receipt: Path | None = None,
    deployed_operator_handoff: Path | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    issues: list[str] = []
    live_evidence: dict[str, Any] = {
        "project_id": "",
        "audiobookshelf_share_url": "",
        "base_url": "https://chummer.run",
        "path": live_import_request.as_posix(),
    }
    if live_import_request.is_file():
        live_evidence, live_issues = _audit_live_import(live_import_request)
        evidence["live_import_request"] = live_evidence
        issues.extend(live_issues)
    else:
        evidence["live_import_request"] = live_evidence
        issues.append("live_import_request_missing")

    if ea_delivery_receipt.is_file() and live_evidence["audiobookshelf_share_url"]:
        delivery_evidence, delivery_issues = _audit_ea_delivery(
            ea_delivery_receipt,
            live_evidence["audiobookshelf_share_url"],
            live_evidence["project_id"],
            live_evidence["base_url"],
        )
        evidence["ea_delivery_receipt"] = delivery_evidence
        issues.extend(delivery_issues)
    elif ea_delivery_receipt.is_file():
        evidence["ea_delivery_receipt"] = {
            "path": ea_delivery_receipt.as_posix(),
            "sha256": _sha256_file(ea_delivery_receipt),
        }
        issues.append("ea_delivery_not_audited_without_live_import_share")
    else:
        evidence["ea_delivery_receipt"] = {"path": ea_delivery_receipt.as_posix()}
        issues.append("ea_delivery_receipt_missing")

    if browser_proof.is_file() and live_evidence["project_id"] and live_evidence["audiobookshelf_share_url"]:
        browser_evidence, browser_issues = _audit_browser_proof(
            browser_proof,
            live_evidence["project_id"],
            live_evidence["audiobookshelf_share_url"],
            live_evidence["base_url"],
        )
        evidence["browser_proof"] = browser_evidence
        issues.extend(browser_issues)
    elif browser_proof.is_file():
        evidence["browser_proof"] = {
            "path": browser_proof.as_posix(),
            "sha256": _sha256_file(browser_proof),
        }
        issues.append("browser_proof_not_audited_without_live_import_project")
    else:
        evidence["browser_proof"] = {"path": browser_proof.as_posix()}
        issues.append("browser_proof_missing")
    readiness_evidence, readiness_issues = _audit_readiness(ea_readiness_receipt)
    if readiness_evidence:
        evidence["ea_readiness_receipt"] = readiness_evidence
    issues.extend(readiness_issues)
    handoff_evidence, handoff_issues = _audit_deployed_operator_handoff(deployed_operator_handoff)
    if handoff_evidence:
        evidence["deployed_operator_handoff"] = handoff_evidence
    issues.extend(handoff_issues)
    issues = sorted(set(issues))
    passed = not issues
    result = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": _now_iso(),
        "status": "pass" if passed else "blocked",
        "finalVerdict": "ORIGIN_DOSSIER_GOLD_READY" if passed else "ORIGIN_DOSSIER_GOLD_BLOCKED",
        "goalCompletionClaimAllowed": passed,
        "claim": "Origin Dossier gold is proven only when live provider import evidence, EA live delivery, and deployed logged-in Chummer playback proof all pass.",
        "failedCodes": issues,
        "evidence": evidence,
    }
    if output is not None:
        _write_json(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit final Chummer Origin Dossier gold E2E evidence.")
    parser.add_argument("--live-import-request", required=True, type=Path)
    parser.add_argument("--ea-delivery-receipt", required=True, type=Path)
    parser.add_argument("--browser-proof", required=True, type=Path)
    parser.add_argument("--ea-readiness-receipt", type=Path)
    parser.add_argument("--deployed-operator-handoff", type=Path)
    parser.add_argument("--output", "--out", dest="output", type=Path)
    parser.add_argument("--require-pass", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    resolved_output = args.output or args.live_import_request.with_name(DEFAULT_OUTPUT_NAME)
    try:
        result = audit(
            live_import_request=args.live_import_request,
            ea_delivery_receipt=args.ea_delivery_receipt,
            browser_proof=args.browser_proof,
            ea_readiness_receipt=args.ea_readiness_receipt,
            deployed_operator_handoff=args.deployed_operator_handoff,
            output=resolved_output,
        )
    except Exception as exc:  # noqa: BLE001 - operator-facing command must fail closed.
        result = {
            "contractName": CONTRACT_NAME,
            "generatedAtUtc": _now_iso(),
            "status": "blocked",
            "finalVerdict": "ORIGIN_DOSSIER_GOLD_BLOCKED",
            "goalCompletionClaimAllowed": False,
            "failedCodes": ["audit_input_error"],
            "error": str(exc),
        }
        _write_json(resolved_output, result)
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    if args.require_pass and result.get("status") != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
