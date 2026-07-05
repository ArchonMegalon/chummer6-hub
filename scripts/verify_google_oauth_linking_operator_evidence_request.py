#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from published_path_hygiene import contains_loopback_url_text

REQUEST_SCRIPT_PATH = SCRIPT_DIR / "materialize_google_oauth_linking_operator_evidence_request.py"
PROOF_SCRIPT_PATH = SCRIPT_DIR / "materialize_google_oauth_linking_proof.py"
DEFAULT_RECEIPT_PATH = SCRIPT_DIR.parents[0] / ".codex-studio" / "published" / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
EXPECTED_STATUSES = {"operator_action_required", "not_required"}


def load_request_module():
    spec = importlib.util.spec_from_file_location(
        "materialize_google_oauth_linking_operator_evidence_request",
        REQUEST_SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"google_oauth_linking_request_module_load_failed:{REQUEST_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_proof_module():
    spec = importlib.util.spec_from_file_location(
        "materialize_google_oauth_linking_proof",
        PROOF_SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"google_oauth_linking_proof_module_load_failed:{PROOF_SCRIPT_PATH}")
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


def verify(path: Path, *, require_pass: bool = False) -> tuple[bool, dict[str, Any]]:
    if not path.is_file():
        result = {
            "contract_name": "",
            "path": str(path),
            "status": "fail",
            "require_pass": require_pass,
            "request_status": "missing",
            "operator_action_still_required": False,
            "recovery_pack_pass": False,
            "issues": [f"missing_google_oauth_linking_operator_evidence_request:{path}"],
        }
        return False, result

    payload = read_json(path)
    request_module = load_request_module()
    proof_module = load_proof_module()

    contract_name = str(payload.get("contract_name") or "").strip()
    request_status = str(payload.get("status") or "").strip()
    base_url = str(payload.get("base_url") or "").strip()
    request_receipt_path = str(payload.get("request_receipt_path") or "").strip()
    required_output_path = str(payload.get("required_output_path") or "").strip()
    required_receipt_path = str(payload.get("required_receipt_path") or "").strip()
    required_operator_evidence_path = str(payload.get("required_operator_evidence_path") or "").strip()
    operator_ask_text_path = str(payload.get("operator_ask_text_path") or "").strip()
    operator_ask_metadata_path = str(payload.get("operator_ask_metadata_path") or "").strip()
    operator_evidence_template_path = str(
        payload.get("operator_evidence_template_path") or payload.get("template_path") or ""
    ).strip()
    release_channel_receipt_path = str(payload.get("release_channel_receipt_path") or "").strip()
    release_version = str(payload.get("release_version") or "").strip()
    release_channel = str(payload.get("release_channel") or "").strip()
    operator_ask_send_command = str(payload.get("operator_ask_send_command") or payload.get("send_command") or "").strip()
    operator_ask_receipt_name = str(payload.get("operator_ask_receipt_name") or payload.get("receipt_name") or "").strip()
    preferred_drop_path = str(payload.get("preferred_drop_path") or "").strip()
    preferred_zip_name = str(payload.get("preferred_zip_name") or "").strip()
    required_zip_filename = str(payload.get("required_zip_filename") or "").strip()
    artifact_intake = payload.get("artifact_intake") if isinstance(payload.get("artifact_intake"), dict) else {}
    operator_telegram_draft = payload.get("operator_telegram_draft") if isinstance(payload.get("operator_telegram_draft"), dict) else {}
    operator_telegram_draft_materialized = (
        payload.get("operator_telegram_draft_materialized")
        if isinstance(payload.get("operator_telegram_draft_materialized"), dict)
        else {}
    )
    expected_patterns = normalized_string_list(payload.get("expected_artifact_patterns"))
    post_import_gates = normalized_string_list(payload.get("post_import_gates"))

    required_evidence_path = Path(required_operator_evidence_path) if required_operator_evidence_path else proof_module.DEFAULT_OPERATOR_EVIDENCE_PATH
    operator_evidence = proof_module.inspect_operator_evidence(base_url or proof_module.DEFAULT_BASE_URL, required_evidence_path)
    request_artifacts = proof_module.inspect_operator_request_artifacts(
        base_url=base_url or proof_module.DEFAULT_BASE_URL,
        operator_evidence_path=required_evidence_path,
        request_receipt_path=path,
        operator_ask_text_path=Path(operator_ask_text_path) if operator_ask_text_path else None,
        operator_ask_metadata_path=Path(operator_ask_metadata_path) if operator_ask_metadata_path else None,
        operator_evidence_template_path=Path(operator_evidence_template_path) if operator_evidence_template_path else None,
    )

    ask_metadata = read_json(Path(operator_ask_metadata_path)) if operator_ask_metadata_path and Path(operator_ask_metadata_path).is_file() else {}
    ask_metadata_status = str(ask_metadata.get("status") or "").strip()

    issues: list[str] = []
    if contract_name != request_module.OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME:
        issues.append("contract_name_mismatch")
    if not str(payload.get("generated_at_utc") or "").strip():
        issues.append("generated_at_utc_missing")
    if request_status not in EXPECTED_STATUSES:
        issues.append("request_status_invalid")
    if str(payload.get("provider") or "").strip() != "browser_operator":
        issues.append("provider_mismatch")
    if not base_url:
        issues.append("base_url_missing")
    if not request_receipt_path:
        issues.append("request_receipt_path_missing")
    elif not paths_match(request_receipt_path, path):
        issues.append("request_receipt_path_mismatch")
    if not required_operator_evidence_path:
        issues.append("required_operator_evidence_path_missing")
    if not paths_match(required_output_path, required_evidence_path):
        issues.append("required_output_path_mismatch")
    if not paths_match(required_receipt_path, required_evidence_path):
        issues.append("required_receipt_path_mismatch")
    if payload.get("required_steps") != list(request_module.REQUIRED_OPERATOR_STEPS):
        issues.append("required_steps_mismatch")
    minimum_screenshot_count = int(payload.get("minimum_screenshot_count") or 0)
    if minimum_screenshot_count < request_module.MINIMUM_OPERATOR_SCREENSHOT_COUNT:
        issues.append("minimum_screenshot_count_too_low")
    recommended_screenshot_paths = payload.get("recommended_screenshot_paths")
    if not isinstance(recommended_screenshot_paths, list) or len(recommended_screenshot_paths) < request_module.MINIMUM_OPERATOR_SCREENSHOT_COUNT:
        issues.append("recommended_screenshot_paths_too_short")
    if not release_channel_receipt_path:
        issues.append("release_channel_receipt_path_missing")
    if not release_version:
        issues.append("release_version_missing")
    if not release_channel:
        issues.append("release_channel_missing")
    if not operator_ask_send_command:
        issues.append("operator_ask_send_command_missing")
    if not operator_ask_receipt_name:
        issues.append("operator_ask_receipt_name_missing")
    if not preferred_drop_path:
        issues.append("preferred_drop_path_missing")
    if not preferred_zip_name:
        issues.append("preferred_zip_name_missing")
    if not required_zip_filename:
        issues.append("required_zip_filename_missing")
    if preferred_drop_path and preferred_zip_name and Path(preferred_drop_path).name != preferred_zip_name:
        issues.append("preferred_drop_filename_mismatch")
    if preferred_zip_name and required_zip_filename and preferred_zip_name != required_zip_filename:
        issues.append("preferred_zip_name_mismatch")
    if payload.get("secrets_redacted") is not True:
        issues.append("secrets_redacted_not_true")
    if payload.get("direct_telegram_sent") is not False:
        issues.append("direct_telegram_sent_not_false")
    if not operator_telegram_draft:
        issues.append("operator_telegram_draft_missing")
    else:
        if not paths_match(
            operator_telegram_draft.get("current_message_path") or operator_telegram_draft.get("message_path"),
            operator_ask_text_path,
        ):
            issues.append("operator_telegram_draft_text_path_mismatch")
        if not paths_match(
            operator_telegram_draft.get("current_metadata_path") or operator_telegram_draft.get("metadata_path"),
            operator_ask_metadata_path,
        ):
            issues.append("operator_telegram_draft_metadata_path_mismatch")
        if str(operator_telegram_draft.get("receipt_name") or "").strip() != str(payload.get("receipt_name") or "").strip():
            issues.append("operator_telegram_draft_receipt_name_mismatch")
        if str(operator_telegram_draft.get("send_command") or "").strip() != str(payload.get("send_command") or "").strip():
            issues.append("operator_telegram_draft_send_command_mismatch")
        if str(operator_telegram_draft.get("receipt_name") or "").strip() != operator_ask_receipt_name:
            issues.append("operator_telegram_draft_operator_ask_receipt_name_mismatch")
        if str(operator_telegram_draft.get("send_command") or "").strip() != operator_ask_send_command:
            issues.append("operator_telegram_draft_operator_ask_send_command_mismatch")
        if request_status == "operator_action_required" and str(operator_telegram_draft.get("status") or "").strip() != "prepared_not_sent":
            issues.append("operator_telegram_draft_status_not_prepared_not_sent")
        if request_status == "not_required" and str(operator_telegram_draft.get("status") or "").strip() != "not_required":
            issues.append("operator_telegram_draft_status_not_not_required")
    if not operator_telegram_draft_materialized:
        issues.append("operator_telegram_draft_materialized_missing")
    else:
        if not paths_match(operator_telegram_draft_materialized.get("operator_ask_text_path"), operator_ask_text_path):
            issues.append("operator_telegram_draft_materialized_text_path_mismatch")
        if not paths_match(operator_telegram_draft_materialized.get("operator_ask_metadata_path"), operator_ask_metadata_path):
            issues.append("operator_telegram_draft_materialized_metadata_path_mismatch")
        if str(operator_telegram_draft_materialized.get("receipt_name") or "").strip() != str(payload.get("receipt_name") or "").strip():
            issues.append("operator_telegram_draft_materialized_receipt_name_mismatch")
        if str(operator_telegram_draft_materialized.get("send_command") or "").strip() != str(payload.get("send_command") or "").strip():
            issues.append("operator_telegram_draft_materialized_send_command_mismatch")
        if str(
            operator_telegram_draft_materialized.get("operator_ask_receipt_name")
            or operator_telegram_draft_materialized.get("receipt_name")
            or ""
        ).strip() != operator_ask_receipt_name:
            issues.append("operator_telegram_draft_materialized_operator_ask_receipt_name_mismatch")
        if str(
            operator_telegram_draft_materialized.get("operator_ask_send_command")
            or operator_telegram_draft_materialized.get("send_command")
            or ""
        ).strip() != operator_ask_send_command:
            issues.append("operator_telegram_draft_materialized_operator_ask_send_command_mismatch")

    if not artifact_intake:
        issues.append("artifact_intake_missing")
    else:
        for field in (
            "discover_command",
            "import_command",
            "auto_import_command",
            "auto_import_watch_command",
            "post_import_verify_command",
        ):
            if not str(artifact_intake.get(field) or "").strip():
                issues.append(f"artifact_intake_{field}_missing")
        if not normalized_string_list(artifact_intake.get("auto_import_roots")):
            issues.append("artifact_intake_auto_import_roots_missing")

    required_patterns = {
        request_module.DEFAULT_BUNDLE_PATTERN,
        preferred_zip_name,
        Path(required_operator_evidence_path).name if required_operator_evidence_path else "",
    }
    if not required_patterns.issubset(set(expected_patterns)):
        issues.append("expected_artifact_patterns_incomplete")

    required_post_import_gates = list(
        getattr(
            request_module,
            "POST_IMPORT_COMMANDS",
            [
                "python3 scripts/materialize_google_oauth_linking_operator_evidence_request.py --base-url https://chummer.run",
                "python3 scripts/verify_google_oauth_linking_operator_evidence_request.py",
                "python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run",
                "python3 scripts/verify_google_oauth_linking_proof.py --require-pass",
                "python3 scripts/verify_flagship_product_readiness_gate.py --summary-output .codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json",
                "python3 scripts/materialize_release_ready_receipt.py",
                "python3 scripts/materialize_operator_release_dashboard.py",
                "python3 scripts/final_gold_janitor.py --skip-materializers",
            ],
        )
    )
    for command in required_post_import_gates:
        if command not in post_import_gates:
            issues.append("post_import_gates_missing_required_command")
            break
    if all(command in post_import_gates for command in required_post_import_gates):
        ordered_indices = [post_import_gates.index(command) for command in required_post_import_gates]
        if ordered_indices != sorted(ordered_indices):
            issues.append("post_import_gates_order_invalid")
    published_commands = [
        str(artifact_intake.get("discover_command") or ""),
        str(artifact_intake.get("import_command") or ""),
        str(artifact_intake.get("auto_import_command") or ""),
        str(artifact_intake.get("auto_import_watch_command") or ""),
        str(artifact_intake.get("post_import_verify_command") or ""),
        *post_import_gates,
    ]
    if any(contains_loopback_url_text(command) for command in published_commands):
        issues.append("published_commands_contain_loopback_url")

    if ask_metadata_status:
        if request_status == "operator_action_required" and ask_metadata_status != "prepared_not_sent":
            issues.append("ask_metadata_status_not_prepared_not_sent")
        if request_status == "not_required" and ask_metadata_status != "not_required":
            issues.append("ask_metadata_status_not_not_required")
    if ask_metadata:
        if str(ask_metadata.get("operator_ask_receipt_name") or ask_metadata.get("receipt_name") or "").strip() != operator_ask_receipt_name:
            issues.append("ask_metadata_operator_ask_receipt_name_mismatch")
        if str(ask_metadata.get("operator_ask_send_command") or ask_metadata.get("send_command") or "").strip() != operator_ask_send_command:
            issues.append("ask_metadata_operator_ask_send_command_mismatch")

    if request_artifacts.get("pass") is not True:
        issues.extend(str(item) for item in request_artifacts.get("failures") or [])

    operator_action_still_required = request_status == "operator_action_required"
    if operator_action_still_required and operator_evidence.get("pass") is True:
        issues.append("operator_action_required_despite_valid_operator_evidence")
    if not operator_action_still_required and operator_evidence.get("pass") is not True:
        issues.append("not_required_without_valid_operator_evidence")
    if require_pass and operator_action_still_required:
        issues.append("operator_action_still_required")

    result = {
        "contract_name": contract_name,
        "path": str(path),
        "status": "pass" if not issues else "fail",
        "require_pass": require_pass,
        "request_status": request_status,
        "operator_action_still_required": operator_action_still_required,
        "recovery_pack_pass": bool(request_artifacts.get("pass")),
        "operator_evidence_pass": bool(operator_evidence.get("pass")),
        "operator_evidence_path": str(required_evidence_path),
        "issues": issues,
    }
    return not issues, result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Google OAuth operator evidence request receipt.")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT_PATH)
    parser.add_argument("--require-pass", action="store_true", default=False)
    args = parser.parse_args()

    ok, result = verify(args.receipt, require_pass=args.require_pass)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
