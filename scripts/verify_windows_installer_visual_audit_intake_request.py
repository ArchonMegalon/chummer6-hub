#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shlex
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from published_path_hygiene import contains_loopback_url_text

REQUEST_SCRIPT_PATH = SCRIPT_DIR / "materialize_windows_installer_visual_audit_intake_request.py"
DEFAULT_RECEIPT_PATH = SCRIPT_DIR.parents[0] / ".codex-studio" / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
EXPECTED_STATUSES = {
    "external_artifact_required",
    "not_required",
    "blocked_missing_promoted_installer_binding",
}
EXPECTED_CONTRACT_NAME = "chummer.windows_installer_visual_audit_intake_request.v1"
PASS_STATUSES = {"pass", "passed", "ready"}


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


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def command_tokens(command: object) -> list[str]:
    text = str(command or "").strip()
    if not text:
        return []
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def command_has_flag(command: object, flag: str) -> bool:
    return flag in command_tokens(command)


def command_flag_value(command: object, flag: str) -> str:
    tokens = command_tokens(command)
    try:
        index = tokens.index(flag)
    except ValueError:
        return ""
    return tokens[index + 1] if index + 1 < len(tokens) else ""


def command_contains_none_path(command: object) -> bool:
    for token in command_tokens(command):
        normalized = token.strip().strip('"\'').replace("\\", "/").lower()
        if normalized == "none" or normalized.endswith("/none"):
            return True
    return False


def normalized_status(value: object) -> str:
    return str(value or "").strip().lower()


def int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def windows_visual_audit_effective_pass_state(payload: object) -> tuple[bool, str, list[str]]:
    if not isinstance(payload, dict):
        return False, "invalid", ["current_windows_visual_audit_invalid"]

    issues: list[str] = []
    raw_status = normalized_status(payload.get("status"))
    failures = normalized_string_list(payload.get("failures"))
    failed_gates = normalized_string_list(payload.get("failed_gates"))
    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    startup_receipt = payload.get("startupReceipt") if isinstance(payload.get("startupReceipt"), dict) else {}
    visual_source = payload.get("visualAuditSource") if isinstance(payload.get("visualAuditSource"), dict) else {}
    artifact_sha = normalize_sha(artifact.get("sha256"))
    actual_artifact_sha = normalize_sha(artifact.get("actualSha256"))
    effective_artifact_sha = normalize_sha(
        payload.get("required_promoted_digest")
        or artifact.get("effectiveSha256")
        or artifact.get("actualSha256")
        or artifact.get("sha256")
    )
    startup_digest = normalize_sha(startup_receipt.get("artifactDigest"))
    visual_digest = normalize_sha(visual_source.get("artifactSha256"))

    if raw_status not in PASS_STATUSES:
        issues.append("current_windows_visual_audit_status_not_pass")
    if failures:
        issues.append("current_windows_visual_audit_has_failures")
    if failed_gates:
        issues.append("current_windows_visual_audit_has_failed_gates")
    if payload.get("pass") is False:
        issues.append("current_windows_visual_audit_explicit_pass_false")
    if not is_sha256(effective_artifact_sha):
        issues.append("current_windows_visual_audit_artifact_digest_missing")
    if not is_sha256(actual_artifact_sha):
        issues.append("current_windows_visual_audit_actual_artifact_digest_missing")
    if artifact_sha and actual_artifact_sha and artifact_sha != actual_artifact_sha:
        issues.append("current_windows_visual_audit_artifact_digest_mismatch")
    if payload.get("source_digest_matches_promoted") is False:
        issues.append("current_windows_visual_audit_source_digest_mismatch")
    if startup_receipt:
        if normalized_status(startup_receipt.get("status")) not in PASS_STATUSES:
            issues.append("current_windows_visual_audit_startup_status_not_pass")
        if normalized_status(startup_receipt.get("verificationDisposition")) == "incompatible_host":
            issues.append("current_windows_visual_audit_startup_incompatible_host")
        if normalized_status(startup_receipt.get("skipClass")) == "incompatible_host":
            issues.append("current_windows_visual_audit_startup_skip_incompatible_host")
        if startup_receipt.get("artifactDigestMatchesPromoted") is False:
            issues.append("current_windows_visual_audit_startup_digest_mismatch")
        if not is_sha256(startup_digest):
            issues.append("current_windows_visual_audit_startup_digest_missing")
        if effective_artifact_sha and startup_digest and effective_artifact_sha != startup_digest:
            issues.append("current_windows_visual_audit_startup_digest_mismatch")
    if visual_source:
        if visual_source.get("exists") is not True:
            issues.append("current_windows_visual_audit_visual_missing")
        if normalized_status(visual_source.get("status")) not in PASS_STATUSES:
            issues.append("current_windows_visual_audit_visual_status_not_pass")
        if normalized_status(visual_source.get("platform")) != "windows":
            issues.append("current_windows_visual_audit_visual_platform_not_windows")
        host_class = normalized_status(visual_source.get("hostClass"))
        if host_class and "windows" not in host_class and host_class != "native":
            issues.append("current_windows_visual_audit_visual_not_native_windows")
        if visual_source.get("artifactDigestMatchesPromoted") is False:
            issues.append("current_windows_visual_audit_visual_digest_mismatch")
        if not is_sha256(visual_digest):
            issues.append("current_windows_visual_audit_visual_digest_missing")
        if effective_artifact_sha and visual_digest and effective_artifact_sha != visual_digest:
            issues.append("current_windows_visual_audit_visual_digest_mismatch")
        required_surfaces = {
            str(item).strip()
            for item in (
                visual_source.get("requiredSurfaces")
                if isinstance(visual_source.get("requiredSurfaces"), list)
                else []
            )
            if str(item).strip()
        }
        if not {"install-progress", "completion"}.issubset(required_surfaces):
            issues.append("current_windows_visual_audit_required_surfaces_incomplete")
        if int_value(visual_source.get("screenshotCount")) < 4:
            issues.append("current_windows_visual_audit_screenshot_count_too_low")
        if int_value(visual_source.get("defaultDpiScreenshotCount")) < 2:
            issues.append("current_windows_visual_audit_default_dpi_count_too_low")
        if int_value(visual_source.get("scaledDpiScreenshotCount")) < 2:
            issues.append("current_windows_visual_audit_scaled_dpi_count_too_low")

    effective_pass = not issues
    return effective_pass, raw_status or "missing", issues


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
    promoted_installer = (
        payload.get("promoted_installer")
        if isinstance(payload.get("promoted_installer"), dict)
        else {}
    )
    installer_file_name = str(promoted_installer.get("file_name") or "").strip()
    promoted_installer_binding_ready = bool(
        is_sha256(promoted_digest)
        and installer_file_name
        and installer_file_name.lower() not in {"none", "null"}
        and Path(installer_file_name).name == installer_file_name
    )
    verifier_binding = (
        payload.get("visual_audit_verifier_binding")
        if isinstance(payload.get("visual_audit_verifier_binding"), dict)
        else {}
    )
    expected_verifier_path = Path(module.visual_audit.VERIFIER_PATH).resolve()
    declared_verifier_path = str(verifier_binding.get("path") or "").strip()
    declared_verifier_sha256 = normalize_sha(verifier_binding.get("sha256"))
    actual_verifier_sha256 = sha256_file(expected_verifier_path)
    expected_verifier_execution_mode = str(
        module.visual_audit.VERIFIER_EXECUTION_MODE
    )
    expected_verifier_contract_name = str(module.visual_audit.CONTRACT_NAME)

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
    if request_status in {"external_artifact_required", "not_required"}:
        if not is_sha256(promoted_digest):
            structural_issues.append("promoted_installer_sha256_invalid")
        if not installer_file_name or installer_file_name.lower() in {"none", "null"}:
            structural_issues.append("promoted_installer_filename_invalid")
        elif Path(installer_file_name).name != installer_file_name:
            structural_issues.append("promoted_installer_filename_invalid")
    elif request_status == "blocked_missing_promoted_installer_binding":
        if promoted_installer_binding_ready:
            structural_issues.append("blocked_request_has_complete_promoted_installer_binding")
    declared_binding_ready = payload.get("promoted_installer_binding_ready")
    if declared_binding_ready is not promoted_installer_binding_ready:
        structural_issues.append("promoted_installer_binding_ready_mismatch")
    if not verifier_binding:
        structural_issues.append("visual_audit_verifier_binding_missing")
    else:
        if not paths_match(declared_verifier_path, expected_verifier_path):
            structural_issues.append("visual_audit_verifier_path_mismatch")
        if str(verifier_binding.get("relative_path") or "").strip() != str(
            module.VISUAL_AUDIT_VERIFIER_RELATIVE_PATH
        ):
            structural_issues.append("visual_audit_verifier_relative_path_mismatch")
        if str(verifier_binding.get("contract_name") or "").strip() != expected_verifier_contract_name:
            structural_issues.append("visual_audit_verifier_contract_name_mismatch")
        if str(verifier_binding.get("execution_mode") or "").strip() != expected_verifier_execution_mode:
            structural_issues.append("visual_audit_verifier_execution_mode_mismatch")
        if not is_sha256(declared_verifier_sha256):
            structural_issues.append("visual_audit_verifier_sha256_invalid")
        elif declared_verifier_sha256 != actual_verifier_sha256:
            structural_issues.append("visual_audit_verifier_sha256_stale")
    if not request_receipt_path:
        structural_issues.append("request_receipt_path_missing")
    elif not paths_match(request_receipt_path, path):
        structural_issues.append("request_receipt_path_mismatch")
    if request_status == "external_artifact_required":
        if not preferred_drop_path:
            structural_issues.append("preferred_drop_path_missing")
        if not required_zip_filename:
            structural_issues.append("required_zip_filename_missing")
        if not preferred_zip_name:
            structural_issues.append("preferred_zip_name_missing")
    elif request_status == "blocked_missing_promoted_installer_binding":
        if preferred_drop_path or required_zip_filename or preferred_zip_name:
            structural_issues.append("blocked_request_exposes_actionable_drop_target")
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
        operator_request_actionable = bool(operator_request.get("actionable"))
        if request_status == "external_artifact_required" and not operator_request_actionable:
            structural_issues.append("operator_request_not_actionable")
        if (
            request_status == "blocked_missing_promoted_installer_binding"
            and operator_request_actionable
        ):
            structural_issues.append("blocked_operator_request_is_actionable")
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
        if request_status == "external_artifact_required" and len(powershell_commands) < 2:
            structural_issues.append("operator_request_powershell_commands_incomplete")
        if (
            request_status == "blocked_missing_promoted_installer_binding"
            and powershell_commands
        ):
            structural_issues.append("blocked_operator_request_has_powershell_commands")
        if any(command_contains_none_path(command) for command in powershell_commands):
            structural_issues.append("operator_request_powershell_command_uses_none_path")

    if not artifact_intake:
        structural_issues.append("artifact_intake_missing")
    else:
        for field in (
            "discover_command",
            "auto_import_command",
            "auto_import_watch_command",
            "watcher_state_path",
            "watcher_pid_file",
            "watcher_log_path",
            "watcher_start_command",
            "watcher_status_command",
            "watcher_stop_command",
            "post_import_verify_command",
        ):
            if not str(artifact_intake.get(field) or "").strip():
                structural_issues.append(f"artifact_intake_{field}_missing")
        import_command = str(artifact_intake.get("import_command") or "").strip()
        if request_status == "external_artifact_required" and not import_command:
            structural_issues.append("artifact_intake_import_command_missing")
        if (
            request_status == "blocked_missing_promoted_installer_binding"
            and import_command
        ):
            structural_issues.append("blocked_artifact_intake_import_command_present")
        if not normalized_string_list(artifact_intake.get("auto_import_roots")):
            structural_issues.append("artifact_intake_auto_import_roots_missing")
        if import_command and not command_has_flag(import_command, "--verify"):
            structural_issues.append("artifact_intake_import_command_missing_verify_flag")
        if import_command and not command_has_flag(import_command, "--intake-request"):
            structural_issues.append("artifact_intake_import_command_missing_intake_request")
        if not command_has_flag(artifact_intake.get("auto_import_command"), "--intake-request"):
            structural_issues.append("artifact_intake_auto_import_command_missing_intake_request")
        if not command_has_flag(artifact_intake.get("auto_import_watch_command"), "--intake-request"):
            structural_issues.append("artifact_intake_auto_import_watch_command_missing_intake_request")
        if not command_has_flag(artifact_intake.get("watcher_start_command"), "--intake-request"):
            structural_issues.append("artifact_intake_watcher_start_command_missing_intake_request")
        if not command_has_flag(artifact_intake.get("watcher_status_command"), "--intake-request"):
            structural_issues.append("artifact_intake_watcher_status_command_missing_intake_request")
        if not command_has_flag(artifact_intake.get("watcher_stop_command"), "--intake-request"):
            structural_issues.append("artifact_intake_watcher_stop_command_missing_intake_request")
        expected_verify_note = str(getattr(module, "POST_IMPORT_VERIFY_NOTE", "")).strip()
        verify_note = str(artifact_intake.get("post_import_verify_note") or "").strip()
        if expected_verify_note and verify_note != expected_verify_note:
            structural_issues.append("artifact_intake_post_import_verify_note_mismatch")
        expected_bound_verify_command = module.build_bound_visual_audit_verify_command(
            verifier_binding
        ) if is_sha256(declared_verifier_sha256) else ""
        post_import_verify_command = str(
            artifact_intake.get("post_import_verify_command") or ""
        ).strip()
        if not expected_bound_verify_command:
            structural_issues.append("artifact_intake_post_import_verify_command_unbound")
        elif post_import_verify_command != expected_bound_verify_command:
            structural_issues.append("artifact_intake_post_import_verify_command_binding_mismatch")
        if (
            command_flag_value(
                post_import_verify_command,
                "--expected-verifier-sha256",
            ).lower()
            != declared_verifier_sha256
        ):
            structural_issues.append("artifact_intake_post_import_verify_command_sha256_mismatch")

    expected_patterns = normalized_string_list(payload.get("expected_artifact_patterns"))
    required_patterns = {
        item
        for item in (
            getattr(module, "DEFAULT_GOLD_PROOF_PATTERN", ""),
            getattr(module, "DEFAULT_VISUAL_SOURCE_PATTERN", ""),
            required_zip_filename,
        )
        if item
    }
    if not required_patterns.issubset(set(expected_patterns)):
        structural_issues.append("expected_artifact_patterns_incomplete")

    post_import_gates = normalized_string_list(payload.get("post_import_gates"))
    expected_bound_verify_command = (
        module.build_bound_visual_audit_verify_command(verifier_binding)
        if is_sha256(declared_verifier_sha256)
        else ""
    )
    required_post_import_gates = [
        expected_bound_verify_command,
        "python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
        "python3 scripts/verify_windows_installer_visual_audit_intake_request.py",
        "python3 scripts/materialize_release_ready_receipt.py --force-global-verifier",
        "python3 scripts/materialize_operator_release_dashboard.py",
        "python3 scripts/final_gold_janitor.py --skip-materializers",
        "python3 ../scripts/release/_release_gate_common.py",
        "python3 ../scripts/attempt_flagship_public_stable_promotion.py --output ../.codex-studio/published/FLAGSHIP_PUBLIC_STABLE_PROMOTION_ATTEMPT.generated.json",
        "python3 ../scripts/materialize_chummer_flagship_surface_stack.py --output ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json",
        "python3 ../scripts/verify_chummer_flagship_surface_stack.py --receipt ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json --require-flagship-pass",
        "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp \"$(date --iso-8601=seconds)\"",
    ]
    for command in required_post_import_gates:
        if not command or command not in post_import_gates:
            structural_issues.append("post_import_gates_missing_required_command")
            break
    if all(command in post_import_gates for command in required_post_import_gates[:3]):
        verify_index = post_import_gates.index(required_post_import_gates[0])
        refresh_index = post_import_gates.index(required_post_import_gates[1])
        verify_request_index = post_import_gates.index(required_post_import_gates[2])
        if not (verify_index < refresh_index < verify_request_index):
            structural_issues.append("post_import_gates_windows_refresh_order_invalid")
    if all(command in post_import_gates for command in required_post_import_gates[5:]):
        final_gold_index = post_import_gates.index(required_post_import_gates[5])
        release_blockers_index = post_import_gates.index(required_post_import_gates[6])
        promotion_attempt_index = post_import_gates.index(required_post_import_gates[7])
        flagship_materialize_index = post_import_gates.index(required_post_import_gates[8])
        flagship_verify_index = post_import_gates.index(required_post_import_gates[9])
        handoff_refresh_index = post_import_gates.index(required_post_import_gates[10])
        if not (
            final_gold_index
            < release_blockers_index
            < promotion_attempt_index
            < flagship_materialize_index
            < flagship_verify_index
            < handoff_refresh_index
        ):
            structural_issues.append("post_import_gates_flagship_refresh_order_invalid")
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
    if request_status == "external_artifact_required" and not send_command:
        structural_issues.append("operator_ask_send_command_missing")
    if (
        request_status == "blocked_missing_promoted_installer_binding"
        and send_command
    ):
        structural_issues.append("blocked_operator_ask_send_command_present")
    if not receipt_name:
        structural_issues.append("operator_ask_receipt_name_missing")
    if not message_preview:
        structural_issues.append("operator_ask_message_preview_missing")

    current_message = read_text_if_file(current_message_path)
    if request_status == "blocked_missing_promoted_installer_binding":
        if str(operator_draft.get("status") or "").strip() != "blocked_not_sendable":
            structural_issues.append("blocked_operator_ask_status_mismatch")
        lowered_message = current_message.lower().replace("\\", "/")
        if "-installerpath" in lowered_message or "/none" in lowered_message:
            structural_issues.append("blocked_operator_ask_contains_actionable_installer_command")
        if "do not run, capture, package, import, or send" not in lowered_message:
            structural_issues.append("blocked_operator_ask_missing_do_not_act_notice")
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
    current_windows_visual_audit_path = normalize_path_text(current_blocker.get("receipt"))
    current_windows_visual_audit_effective_pass = False
    current_windows_visual_audit_status = "missing"
    current_windows_visual_audit_issues: list[str] = []
    current_windows_visual_audit_promoted_digest = ""
    if current_windows_visual_audit_path:
        current_windows_visual_audit_receipt = Path(current_windows_visual_audit_path)
        if current_windows_visual_audit_receipt.is_file():
            try:
                current_windows_visual_audit_payload = read_json(current_windows_visual_audit_receipt)
            except (json.JSONDecodeError, ValueError):
                current_windows_visual_audit_status = "invalid"
                current_windows_visual_audit_issues = ["current_windows_visual_audit_invalid"]
            else:
                current_windows_visual_audit_artifact = (
                    current_windows_visual_audit_payload.get("artifact")
                    if isinstance(current_windows_visual_audit_payload.get("artifact"), dict)
                    else {}
                )
                current_windows_visual_audit_promoted_digest = normalize_sha(
                    current_windows_visual_audit_payload.get("required_promoted_digest")
                    or current_windows_visual_audit_artifact.get("effectiveSha256")
                    or current_windows_visual_audit_artifact.get("actualSha256")
                    or current_windows_visual_audit_artifact.get("sha256")
                )
                (
                    current_windows_visual_audit_effective_pass,
                    current_windows_visual_audit_status,
                    current_windows_visual_audit_issues,
                ) = windows_visual_audit_effective_pass_state(current_windows_visual_audit_payload)
                if (
                    is_sha256(promoted_digest)
                    and is_sha256(current_windows_visual_audit_promoted_digest)
                    and current_windows_visual_audit_promoted_digest != promoted_digest
                ):
                    current_windows_visual_audit_effective_pass = False
                    current_windows_visual_audit_issues.append(
                        "current_windows_visual_audit_promoted_digest_mismatch"
                    )
        else:
            current_windows_visual_audit_issues = ["current_windows_visual_audit_missing"]

    effective_request_status = (
        "not_required"
        if current_windows_visual_audit_effective_pass
        else (
            "blocked_missing_promoted_installer_binding"
            if request_status == "blocked_missing_promoted_installer_binding"
            else "external_artifact_required"
        )
    )

    if request_status == "not_required" and not current_windows_visual_audit_effective_pass:
        issues.append("not_required_without_valid_current_windows_visual_audit")
    if request_status == "external_artifact_required" and current_windows_visual_audit_effective_pass:
        issues.append("external_artifact_required_despite_valid_current_windows_visual_audit")
    if (
        request_status == "blocked_missing_promoted_installer_binding"
        and current_windows_visual_audit_effective_pass
    ):
        issues.append("blocked_request_despite_valid_current_windows_visual_audit")
    if require_pass:
        if effective_request_status != "not_required":
            issues.append("external_artifact_still_required")

    result = {
        "contract_name": getattr(module, "CONTRACT_NAME", ""),
        "path": str(path),
        "status": "pass" if not issues else "fail",
        "require_pass": require_pass,
        "request_status": request_status or "missing",
        "operator_action_still_required": (
            effective_request_status == "external_artifact_required"
            and promoted_installer_binding_ready
        ),
        "recovery_pack_pass": not structural_issues,
        "structural_status": "pass" if not structural_issues else "fail",
        "effective_status": effective_request_status,
        "issues": issues,
        "structural_issues": structural_issues,
        "current_windows_visual_audit_path": current_windows_visual_audit_path,
        "current_windows_visual_audit_status": current_windows_visual_audit_status,
        "current_windows_visual_audit_effective_pass": current_windows_visual_audit_effective_pass,
        "current_windows_visual_audit_issues": current_windows_visual_audit_issues,
        "current_windows_visual_audit_promoted_installer_sha256": current_windows_visual_audit_promoted_digest,
        "promoted_installer_sha256": promoted_digest,
        "promoted_installer_file_name": installer_file_name,
        "promoted_installer_binding_ready": promoted_installer_binding_ready,
        "visual_audit_verifier_path": declared_verifier_path,
        "visual_audit_verifier_sha256_expected": declared_verifier_sha256,
        "visual_audit_verifier_sha256_actual": actual_verifier_sha256,
        "visual_audit_verifier_sha256_matches_current": bool(
            is_sha256(declared_verifier_sha256)
            and declared_verifier_sha256 == actual_verifier_sha256
        ),
        "visual_audit_verifier_execution_mode": str(
            verifier_binding.get("execution_mode") or ""
        ),
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
