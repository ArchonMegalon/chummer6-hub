#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_verify_paths import deployed_operator_handoff_from_env


CONTRACT_NAME = "chummer.origin_edition.deployed_operator_handoff.v1"
REQUIRED_COMMAND_SNIPPETS = (
    "materialize_origin_dossier_deployed_browser_probe.py",
    "audit_origin_dossier_gold_e2e.py",
    "materialize_origin_edition_gold_proof_chain.py",
    "materialize_origin_edition_gold_final_verdict.py",
    "verify_origin_edition_gold_proof_chain.py",
    "verify_origin_edition_gold_final_verdict.py",
    "CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD=1 bash scripts/ai/run_services_verification.sh",
)
REQUIRED_CONTEXT_ARGUMENTS = (
    "--project-id ",
    "--family-name ",
    "--given-name ",
    "--runner-name ",
    "--namespace ",
    "--base-url ",
)
REQUIRED_CONTEXT_COMMANDS = (
    "materialize_origin_dossier_deployed_browser_probe.py",
    "materialize_origin_edition_gold_proof_chain.py",
    "materialize_origin_edition_gold_final_verdict.py",
)
REQUIRED_DEPLOYED_PROBE_FLAGS = (
    "logged_in_browser_verified",
    "selected_face_cover_marker_visible",
    "selected_face_cover_alt_visible",
    "selected_face_cover_route_visible",
    "selected_face_cover_visible",
    "read_tab_visible",
    "read_section_visible",
    "listen_tab_visible",
    "listen_section_visible",
    "watch_tab_visible",
    "watch_section_visible",
    "canon_audit_tab_visible",
    "canon_audit_section_visible",
    "chummer_canon_owner_visible",
    "provider_created_facts_blocked_visible",
    "canon_privacy_receipts_present",
    "no_fallback_media_verified",
    "canon_audit_content_verified",
    "read_gate_verified",
    "chummer_run_listen_gate_verified",
    "watch_gate_verified",
    "cover_route_verified",
    "book_route_verified",
    "watch_artifact_nonempty",
    "cover_artifact_nonempty",
    "book_artifact_nonempty",
    "cover_sha_matches_import",
    "book_sha_matches_import",
    "video_sha_matches_import",
    "audiobook_share_url_trusted",
    "dossier_share_url_trusted",
    "audiobook_share_reachable",
    "dossier_share_reachable",
    "owner_playback_e2e_verified",
    "unauthenticated_detail_redirect_verified",
    "unauthenticated_read_redirect_verified",
    "unauthenticated_listen_redirect_verified",
    "unauthenticated_book_redirect_verified",
    "unauthenticated_cover_redirect_verified",
    "unauthenticated_video_redirect_verified",
    "all_private_routes_login_protected",
)
FORBIDDEN_VALUE_MARKERS = (
    "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN=",
    "Bearer ",
    "Cookie:",
    "secret-token",
    "owner-session-token",
    "secret-session",
    "secret-bearer-session",
    "super-secret",
    "rangersofB5",
    "api:",
    "api.telegram.org/bot",
    "TELEGRAM_BOT_TOKEN=",
    "EA_TELEGRAM_BOT_TOKEN=",
    "UNMIXR_API_KEY=",
    "audiobookshelf_api_token=",
    "telegram_bot_token=",
)


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def verify(path: Path, *, require_pass: bool = False) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not path.is_file():
        return False, [f"missing_deployed_operator_handoff:{path}"]
    text = path.read_text(encoding="utf-8")
    for marker in FORBIDDEN_VALUE_MARKERS:
        if marker in text:
            issues.append(f"forbidden_secret_marker:{marker}")
    try:
        payload = read_json(path)
    except (json.JSONDecodeError, ValueError) as exc:
        issues.append(f"invalid_json:{exc.__class__.__name__}")
        return False, issues

    if payload.get("contractName") != CONTRACT_NAME:
        issues.append("contract_name_mismatch")
    status = str(payload.get("status") or "")
    if status not in {"pass", "ready_for_operator_token", "blocked"}:
        issues.append(f"unexpected_status:{status}")
    if require_pass and status != "pass":
        issues.append("handoff_not_pass")
    if payload.get("goalCompletionClaimAllowed") is not False:
        issues.append("handoff_must_not_claim_goal_completion")
    if not str(payload.get("updated_at") or "").strip():
        issues.append("updated_at_missing")
    if not str(payload.get("next_action") or "").strip():
        issues.append("next_action_missing")
    blocking_reason = str(payload.get("blocking_reason") or "")
    if status == "pass" and blocking_reason:
        issues.append("pass_handoff_has_blocking_reason")
    if status != "pass" and not blocking_reason:
        issues.append("blocked_handoff_missing_blocking_reason")
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    if not isinstance(progress.get("blockerCount"), int):
        issues.append("progress_blocker_count_missing")

    required_env = payload.get("requiredEnv") if isinstance(payload.get("requiredEnv"), dict) else {}
    token_env = required_env.get("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN") if isinstance(required_env.get("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN"), dict) else {}
    release_env = required_env.get("CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD") if isinstance(required_env.get("CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD"), dict) else {}
    if token_env.get("required") is not True:
        issues.append("identity_token_not_marked_required")
    if token_env.get("valueStoredInReceipt") is not False:
        issues.append("identity_token_value_stored")
    if release_env.get("requiredForRelease") is not True:
        issues.append("release_gold_env_not_required")
    if release_env.get("expectedValueForRelease") != "1":
        issues.append("release_gold_env_expected_value_not_1")
    if release_env.get("valueStoredInReceipt") is not False:
        issues.append("release_gold_env_value_stored")

    env_file = payload.get("envFile") if isinstance(payload.get("envFile"), dict) else {}
    if env_file.get("valuesStoredInReceipt") is not False:
        issues.append("env_file_values_stored")

    commands = payload.get("requiredCommands") if isinstance(payload.get("requiredCommands"), list) else []
    serialized_commands = "\n".join(str(command) for command in commands)
    for snippet in REQUIRED_COMMAND_SNIPPETS:
        if snippet not in serialized_commands:
            issues.append(f"required_command_missing:{snippet}")
    for argument in REQUIRED_CONTEXT_ARGUMENTS:
        if argument not in serialized_commands:
            issues.append(f"required_context_argument_missing:{argument.strip()}")
    for command_name in REQUIRED_CONTEXT_COMMANDS:
        matching = [str(command) for command in commands if command_name in str(command)]
        if not matching:
            continue
        command_text = "\n".join(matching)
        for argument in REQUIRED_CONTEXT_ARGUMENTS:
            if argument not in command_text:
                issues.append(f"required_context_argument_missing:{command_name}:{argument.strip()}")
    if "--require-gold" not in serialized_commands:
        issues.append("strict_gold_verifier_missing")
    if "--allow-blocked" not in serialized_commands:
        issues.append("blocked_materialization_command_missing")

    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    for key in ("projectId", "familyName", "givenName", "runnerName", "namespace", "baseUrl"):
        if not str(context.get(key) or "").strip():
            issues.append(f"context_field_missing:{key}")

    current = payload.get("currentEvidence") if isinstance(payload.get("currentEvidence"), dict) else {}
    required_flags = current.get("deployedProbeRequiredFlags") if isinstance(current.get("deployedProbeRequiredFlags"), dict) else {}
    missing_flags = current.get("deployedProbeMissingRequiredFlags") if isinstance(current.get("deployedProbeMissingRequiredFlags"), list) else []
    required_flag_keys = set(required_flags)
    expected_flag_keys = set(REQUIRED_DEPLOYED_PROBE_FLAGS)
    if required_flag_keys != expected_flag_keys:
        missing_required = sorted(expected_flag_keys - required_flag_keys)
        extra_required = sorted(required_flag_keys - expected_flag_keys)
        if missing_required:
            issues.append(f"deployed_probe_required_flags_missing:{missing_required}")
        if extra_required:
            issues.append(f"deployed_probe_required_flags_unexpected:{extra_required}")
    if not str(current.get("deployedProbeNextAction") or "").strip():
        issues.append("deployed_probe_next_action_missing")
    if status != "pass" and not str(current.get("deployedProbeBlockingReason") or "").strip():
        issues.append("deployed_probe_blocking_reason_missing")
    if not isinstance(current.get("deployedProbeProgress"), dict):
        issues.append("deployed_probe_progress_missing")
    if status == "pass":
        if payload.get("blockers") != []:
            issues.append("pass_handoff_has_blockers")
        if missing_flags != []:
            issues.append("pass_handoff_has_missing_deployed_flags")
        if any(value is not True for value in required_flags.values()):
            issues.append("pass_handoff_required_flag_not_true")
        if token_env.get("presentInCurrentProcess") is not True:
            issues.append("pass_handoff_token_not_present")
    if status == "ready_for_operator_token":
        blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
        if "missing_deployed_identity_token" not in blockers:
            issues.append("ready_handoff_missing_identity_token_blocker")
        if token_env.get("presentInCurrentProcess") is not False:
            issues.append("ready_handoff_token_presence_not_false")

    privacy = payload.get("privacy") if isinstance(payload.get("privacy"), dict) else {}
    for key in ("rawCredentialExposed", "rawSessionTokenExposed", "envValuesExposed", "deploymentPerformed"):
        if privacy.get(key) is not False:
            issues.append(f"privacy_flag_not_false:{key}")
    return not issues, issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the secret-safe deployed operator handoff receipt.")
    parser.add_argument(
        "--handoff",
        type=Path,
    )
    parser.add_argument("--require-pass", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    handoff = args.handoff or deployed_operator_handoff_from_env()
    ok, issues = verify(handoff, require_pass=args.require_pass)
    if not ok:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    print("origin dossier deployed operator handoff verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
