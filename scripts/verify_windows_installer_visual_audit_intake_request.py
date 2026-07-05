#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from published_path_hygiene import contains_loopback_url_text


REQUEST_SCRIPT_PATH = SCRIPT_DIR / "materialize_windows_installer_visual_audit_intake_request.py"
DEFAULT_RECEIPT_PATH = SCRIPT_DIR.parent / ".codex-studio" / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
EXPECTED_STATUSES = {"external_artifact_required", "not_required"}
EXPECTED_CONTRACT_NAME = "chummer.windows_installer_visual_audit_intake_request.v1"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "materialize_windows_installer_visual_audit_intake_request",
        REQUEST_SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"windows_visual_intake_module_load_failed:{REQUEST_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object")
    return payload


def normalized_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_sha(value: object) -> str:
    return str(value or "").strip().lower().removeprefix("sha256:")


def is_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def normalize_path_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return str(Path(text).expanduser())


def paths_match(left: object, right: object) -> bool:
    left_text = normalize_path_text(left)
    right_text = normalize_path_text(right)
    if not left_text or not right_text:
        return False
    try:
        return Path(left_text).resolve() == Path(right_text).resolve()
    except OSError:
        return left_text == right_text


def path_exists(path_value: object) -> bool:
    text = normalize_path_text(path_value)
    if not text:
        return False
    try:
        return Path(text).is_file()
    except OSError:
        return False


def read_text_if_file(path_value: object) -> str:
    text = normalize_path_text(path_value)
    if not text:
        return ""
    path = Path(text)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().lower()


def verify(path: Path, *, require_pass: bool = False) -> tuple[bool, dict[str, Any]]:
    if not path.is_file():
        result = {
            "contract_name": EXPECTED_CONTRACT_NAME,
            "path": str(path),
            "status": "fail",
            "require_pass": require_pass,
            "request_status": "missing",
            "operator_action_still_required": False,
            "recovery_pack_pass": False,
            "structural_status": "missing",
            "effective_status": "missing",
            "issues": [f"missing_windows_visual_intake_request:{path}"],
        }
        return False, result

    try:
        payload = read_json(path)
    except (json.JSONDecodeError, ValueError):
        result = {
            "contract_name": EXPECTED_CONTRACT_NAME,
            "path": str(path),
            "status": "fail",
            "require_pass": require_pass,
            "request_status": "invalid",
            "operator_action_still_required": False,
            "recovery_pack_pass": False,
            "structural_status": "invalid",
            "effective_status": "invalid",
            "issues": [f"malformed_windows_visual_intake_request:{path}"],
        }
        return False, result

    module = load_module()
    contract_name = str(payload.get("contract_name") or "").strip()
    request_status = str(payload.get("status") or "").strip()
    request_receipt_path = str(payload.get("request_receipt_path") or "").strip()
    promoted_digest = normalize_sha(
        payload.get("promoted_installer_sha256")
        or dict(payload.get("promoted_installer") or {}).get("sha256")
        or dict(payload.get("artifact") or {}).get("sha256")
    )
    preferred_drop_path = str(payload.get("preferred_drop_path") or "").strip()
    required_zip_filename = str(payload.get("required_zip_filename") or "").strip()
    preferred_zip_name = str(payload.get("preferred_zip_name") or "").strip()
    operator_request = payload.get("operator_request") if isinstance(payload.get("operator_request"), dict) else {}
    operator_draft = payload.get("operator_telegram_draft") if isinstance(payload.get("operator_telegram_draft"), dict) else {}
    operator_draft_materialized = (
        payload.get("operator_telegram_draft_materialized")
        if isinstance(payload.get("operator_telegram_draft_materialized"), dict)
        else {}
    )
    artifact_intake = payload.get("artifact_intake") if isinstance(payload.get("artifact_intake"), dict) else {}
    current_blocker = payload.get("current_blocker") if isinstance(payload.get("current_blocker"), dict) else {}

    structural_issues: list[str] = []
    if contract_name != getattr(module, "CONTRACT_NAME", ""):
        structural_issues.append("contract_name_mismatch")
    if not str(payload.get("generated_at_utc") or "").strip():
        structural_issues.append("generated_at_utc_missing")
    if request_status not in EXPECTED_STATUSES:
        structural_issues.append("request_status_invalid")
    if str(payload.get("provider") or "").strip() != "native_windows_operator":
        structural_issues.append("provider_mismatch")
    if not str(payload.get("release_channel_receipt_path") or "").strip():
        structural_issues.append("release_channel_receipt_path_missing")
    if not str(payload.get("release_version") or "").strip():
        structural_issues.append("release_version_missing")
    if not str(payload.get("release_channel") or "").strip():
        structural_issues.append("release_channel_missing")
    if not is_sha256(promoted_digest):
        structural_issues.append("promoted_installer_sha256_invalid")
    if not request_receipt_path:
        structural_issues.append("request_receipt_path_missing")
    elif not paths_match(request_receipt_path, path):
        structural_issues.append("request_receipt_path_mismatch")
    if not preferred_drop_path:
        structural_issues.append("preferred_drop_path_missing")
    if not required_zip_filename:
        structural_issues.append("required_zip_filename_missing")
    if not preferred_zip_name:
        structural_issues.append("preferred_zip_name_missing")
    if preferred_drop_path and required_zip_filename and Path(preferred_drop_path).name != required_zip_filename:
        structural_issues.append("preferred_drop_filename_mismatch")
    if preferred_zip_name and required_zip_filename and preferred_zip_name != required_zip_filename:
        structural_issues.append("preferred_zip_name_mismatch")
    if payload.get("secrets_redacted") is not True:
        structural_issues.append("secrets_redacted_not_true")
    if payload.get("direct_telegram_sent") is not False:
        structural_issues.append("direct_telegram_sent_not_false")
    if not str(current_blocker.get("receipt") or "").strip():
        structural_issues.append("current_blocker_receipt_missing")

    if not operator_request:
        structural_issues.append("operator_request_missing")
    else:
        required_surfaces = set(normalized_string_list(operator_request.get("required_surfaces")))
        missing_surfaces = [
            surface
            for surface in getattr(module.visual_audit, "REQUIRED_SURFACES", [])
            if surface not in required_surfaces
        ]
        if missing_surfaces:
            structural_issues.append("operator_request_required_surfaces_incomplete")
        required_dpi_scales = set(normalized_string_list(operator_request.get("required_dpi_scales")))
        if not {"1.0", "1.5"}.issubset(required_dpi_scales):
            structural_issues.append("operator_request_required_dpi_scales_incomplete")
        if str(operator_request.get("required_host_class_prefix") or "").strip() != "native-windows":
            structural_issues.append("operator_request_host_class_prefix_mismatch")
        if not str(operator_request.get("summary") or "").strip():
            structural_issues.append("operator_request_summary_missing")
        powershell_commands = normalized_string_list(operator_request.get("powershell_commands"))
        if len(powershell_commands) < 2:
            structural_issues.append("operator_request_powershell_commands_incomplete")

    if not artifact_intake:
        structural_issues.append("artifact_intake_missing")
    else:
        for field in (
            "discover_command",
            "import_command",
            "auto_import_command",
            "auto_import_watch_command",
            "post_import_verify_command",
        ):
            if not str(artifact_intake.get(field) or "").strip():
                structural_issues.append(f"artifact_intake_{field}_missing")
        if not normalized_string_list(artifact_intake.get("auto_import_roots")):
            structural_issues.append("artifact_intake_auto_import_roots_missing")

    expected_patterns = normalized_string_list(payload.get("expected_artifact_patterns"))
    required_patterns = {
        getattr(module, "DEFAULT_GOLD_PROOF_PATTERN", ""),
        getattr(module, "DEFAULT_VISUAL_SOURCE_PATTERN", ""),
        required_zip_filename,
    }
    if not required_patterns.issubset(set(expected_patterns)):
        structural_issues.append("expected_artifact_patterns_incomplete")

    post_import_gates = normalized_string_list(payload.get("post_import_gates"))
    required_post_import_gates = [
        "python3 scripts/verify_windows_installer_visual_audit.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
        "python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
        "python3 scripts/verify_windows_installer_visual_audit_intake_request.py",
        "python3 scripts/materialize_release_ready_receipt.py",
        "python3 scripts/materialize_operator_release_dashboard.py",
    ]
    for command in required_post_import_gates:
        if command not in post_import_gates:
            structural_issues.append("post_import_gates_missing_required_command")
            break
    if all(command in post_import_gates for command in required_post_import_gates[:3]):
        verify_index = post_import_gates.index(required_post_import_gates[0])
        refresh_index = post_import_gates.index(required_post_import_gates[1])
        verify_request_index = post_import_gates.index(required_post_import_gates[2])
        if not (verify_index < refresh_index < verify_request_index):
            structural_issues.append("post_import_gates_windows_refresh_order_invalid")
    published_commands = [
        str(artifact_intake.get("discover_command") or ""),
        str(artifact_intake.get("import_command") or ""),
        str(artifact_intake.get("auto_import_command") or ""),
        str(artifact_intake.get("auto_import_watch_command") or ""),
        str(artifact_intake.get("post_import_verify_command") or ""),
        *post_import_gates,
    ]
    if any(contains_loopback_url_text(command) for command in published_commands):
        structural_issues.append("published_commands_contain_loopback_url")

    current_message_path = str(
        operator_draft.get("current_message_path")
        or operator_draft_materialized.get("operator_ask_text_path")
        or operator_draft_materialized.get("current_message_path")
        or ""
    ).strip()
    current_metadata_path = str(
        operator_draft.get("current_metadata_path")
        or operator_draft_materialized.get("operator_ask_metadata_path")
        or operator_draft_materialized.get("current_metadata_path")
        or ""
    ).strip()
    message_path = str(
        operator_draft.get("message_path")
        or operator_draft_materialized.get("message_path")
        or ""
    ).strip()
    metadata_path = str(
        operator_draft.get("metadata_path")
        or operator_draft_materialized.get("source_metadata_path")
        or ""
    ).strip()
    send_command = str(
        operator_draft.get("send_command")
        or operator_draft_materialized.get("operator_ask_send_command")
        or operator_draft_materialized.get("send_command")
        or ""
    ).strip()
    receipt_name = str(
        operator_draft.get("receipt_name")
        or operator_draft_materialized.get("operator_ask_receipt_name")
        or operator_draft_materialized.get("receipt_name")
        or ""
    ).strip()
    message_preview = str(
        operator_draft.get("message_preview")
        or operator_draft_materialized.get("message_preview")
        or ""
    ).strip()

    if not current_message_path:
        structural_issues.append("operator_ask_current_message_path_missing")
    elif not path_exists(current_message_path):
        structural_issues.append("operator_ask_current_message_missing")
    if not current_metadata_path:
        structural_issues.append("operator_ask_current_metadata_path_missing")
    elif not path_exists(current_metadata_path):
        structural_issues.append("operator_ask_current_metadata_missing")
    if not send_command:
        structural_issues.append("operator_ask_send_command_missing")
    if not receipt_name:
        structural_issues.append("operator_ask_receipt_name_missing")
    if not message_preview:
        structural_issues.append("operator_ask_message_preview_missing")

    current_message = read_text_if_file(current_message_path)
    current_message_sha = sha256_text(current_message) if current_message else ""
    declared_message_sha = str(
        operator_draft.get("message_sha256")
        or operator_draft_materialized.get("message_sha256")
        or ""
    ).strip()
    if declared_message_sha and current_message_sha and declared_message_sha != current_message_sha:
        structural_issues.append("operator_ask_message_sha256_mismatch")

    current_metadata_payload: dict[str, Any] = {}
    if path_exists(current_metadata_path):
        try:
            current_metadata_payload = read_json(Path(normalize_path_text(current_metadata_path)))
        except Exception:
            structural_issues.append("operator_ask_current_metadata_invalid")
            current_metadata_payload = {}
    if current_metadata_payload:
        if not paths_match(current_metadata_payload.get("request_receipt_path"), request_receipt_path):
            structural_issues.append("operator_ask_current_metadata_request_receipt_path_mismatch")
        if not paths_match(current_metadata_payload.get("current_message_path"), current_message_path):
            structural_issues.append("operator_ask_current_metadata_current_message_path_mismatch")
        if normalize_sha(current_metadata_payload.get("promoted_installer_sha256")) != promoted_digest:
            structural_issues.append("operator_ask_current_metadata_promoted_digest_mismatch")
        if str(current_metadata_payload.get("preferred_drop_path") or "").strip() != preferred_drop_path:
            structural_issues.append("operator_ask_current_metadata_preferred_drop_path_mismatch")
        if str(current_metadata_payload.get("send_command") or "").strip() != send_command:
            structural_issues.append("operator_ask_current_metadata_send_command_mismatch")
        if str(current_metadata_payload.get("receipt_name") or "").strip() != receipt_name:
            structural_issues.append("operator_ask_current_metadata_receipt_name_mismatch")
        metadata_message_sha = str(current_metadata_payload.get("message_sha256") or "").strip()
        if metadata_message_sha and current_message_sha and metadata_message_sha != current_message_sha:
            structural_issues.append("operator_ask_current_metadata_message_sha256_mismatch")
        if current_metadata_payload.get("secrets_redacted") is not True:
            structural_issues.append("operator_ask_current_metadata_secrets_redacted_not_true")

        source_message_path = str(current_metadata_payload.get("source_message_path") or message_path).strip()
        if source_message_path and not path_exists(source_message_path):
            structural_issues.append("operator_ask_source_message_missing")
        elif source_message_path and current_message and read_text_if_file(source_message_path) != current_message:
            structural_issues.append("operator_ask_source_message_mismatch")

        source_metadata_path = str(current_metadata_payload.get("source_metadata_path") or metadata_path).strip()
        if source_metadata_path and not path_exists(source_metadata_path):
            structural_issues.append("operator_ask_source_metadata_missing")
        elif source_metadata_path:
            try:
                source_metadata_payload = read_json(Path(normalize_path_text(source_metadata_path)))
            except Exception:
                structural_issues.append("operator_ask_source_metadata_invalid")
            else:
                if not paths_match(source_metadata_payload.get("request_receipt_path"), request_receipt_path):
                    structural_issues.append("operator_ask_source_metadata_request_receipt_path_mismatch")
                if str(source_metadata_payload.get("send_command") or "").strip() != send_command:
                    structural_issues.append("operator_ask_source_metadata_send_command_mismatch")
                if str(source_metadata_payload.get("receipt_name") or "").strip() != receipt_name:
                    structural_issues.append("operator_ask_source_metadata_receipt_name_mismatch")
                source_metadata_message_sha = str(source_metadata_payload.get("message_sha256") or "").strip()
                if source_metadata_message_sha and current_message_sha and source_metadata_message_sha != current_message_sha:
                    structural_issues.append("operator_ask_source_metadata_message_sha256_mismatch")

    issues = list(structural_issues)
    if require_pass and request_status != "not_required":
        issues.append("external_artifact_still_required")

    result = {
        "contract_name": getattr(module, "CONTRACT_NAME", ""),
        "path": str(path),
        "status": "pass" if not issues else "fail",
        "require_pass": require_pass,
        "request_status": request_status or "missing",
        "operator_action_still_required": request_status == "external_artifact_required",
        "recovery_pack_pass": not structural_issues,
        "structural_status": "pass" if not structural_issues else "fail",
        "effective_status": request_status or "missing",
        "issues": issues,
        "structural_issues": structural_issues,
        "promoted_installer_sha256": promoted_digest,
        "preferred_drop_path": preferred_drop_path,
        "request_receipt_path": request_receipt_path,
        "operator_ask_text_path": current_message_path,
        "operator_ask_metadata_path": current_metadata_path,
        "operator_ask_send_command": send_command,
        "operator_ask_receipt_name": receipt_name,
    }
    return not issues, result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Windows installer visual-audit intake request receipt."
    )
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT_PATH)
    parser.add_argument("--require-pass", action="store_true", default=False)
    args = parser.parse_args()

    ok, result = verify(args.receipt, require_pass=args.require_pass)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
