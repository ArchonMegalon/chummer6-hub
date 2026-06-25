#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_verify_paths import gold_requirement_coverage_from_env


CONTRACT_NAME = "chummer.origin_edition.gold_requirement_coverage.v1"
EXPECTED_REQUIREMENTS = (
    "approved_sample_runner_canon_only",
    "provider_story_and_humanizer_pipeline",
    "canon_privacy_audit",
    "cover_consistency_all_surfaces",
    "ebook_pdf_dossier_packaging",
    "m4b_unmixr_audiobook_packaging",
    "audiobookshelf_dossier_and_audiobook_share",
    "movie_story_scene_playback",
    "local_authenticated_chummer_route",
    "runsite_handoff_constraints",
    "telegram_origin_links",
    "no_fallback_no_sentinel_no_direct_publish_no_secrets",
    "deployed_owner_read_listen_watch_canon",
)
CURRENT_ALLOWED_BLOCKED_REQUIREMENTS = ["deployed_owner_read_listen_watch_canon"]
FORBIDDEN_VALUE_MARKERS = (
    "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN=",
    "Bearer ",
    "Cookie:",
    "secret-token",
    "owner-session-token",
    "super-secret",
    "rangersofB5",
    "api:",
)


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def valid_sha(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text.lower())


def verify(path: Path, *, require_gold: bool = False) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not path.is_file():
        return False, [f"missing_requirement_coverage:{path}"]
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
    if not valid_sha(payload.get("matrixSha256")):
        issues.append("matrix_sha256_invalid")
    if not valid_sha(payload.get("proofChainSha256")):
        issues.append("proof_chain_sha256_invalid")

    requirements = payload.get("requirements") if isinstance(payload.get("requirements"), list) else []
    requirement_ids = [str(item.get("id") or "") for item in requirements if isinstance(item, dict)]
    if requirement_ids != list(EXPECTED_REQUIREMENTS):
        issues.append(f"requirement_order_mismatch:{requirement_ids}")

    blocked_requirements = payload.get("blockedRequirements") if isinstance(payload.get("blockedRequirements"), list) else []
    blocked_requirements = [str(item) for item in blocked_requirements]
    computed_blocked: list[str] = []
    for item in requirements:
        if not isinstance(item, dict):
            issues.append("requirement_not_object")
            continue
        requirement_id = str(item.get("id") or "")
        status = str(item.get("status") or "")
        if status not in {"proved", "blocked"}:
            issues.append(f"requirement_status_invalid:{requirement_id}:{status}")
        if status == "blocked":
            computed_blocked.append(requirement_id)
            has_reason = any(
                isinstance(item.get(key), list) and bool(item.get(key))
                for key in ("missingRows", "blockedRows", "missingHardGates", "blockedHardGates")
            )
            if not has_reason:
                issues.append(f"blocked_requirement_without_reason:{requirement_id}")
        if status == "proved":
            for key in ("missingRows", "blockedRows", "missingHardGates", "blockedHardGates"):
                if item.get(key) not in ([], None):
                    issues.append(f"proved_requirement_has_blockers:{requirement_id}:{key}")

    if blocked_requirements != computed_blocked:
        issues.append(f"blocked_requirement_mismatch:{blocked_requirements}:{computed_blocked}")

    status = str(payload.get("status") or "")
    if require_gold:
        if status != "pass":
            issues.append("coverage_not_pass")
        if payload.get("goalCompletionClaimAllowed") is not True:
            issues.append("coverage_goal_completion_not_allowed")
        if blocked_requirements:
            issues.append("coverage_has_blocked_requirements")
    else:
        if status not in {"pass", "blocked"}:
            issues.append(f"unexpected_status:{status}")
        if status == "blocked":
            if blocked_requirements != CURRENT_ALLOWED_BLOCKED_REQUIREMENTS:
                issues.append(f"unexpected_blocked_requirements:{blocked_requirements}")
            if payload.get("goalCompletionClaimAllowed") is not False:
                issues.append("blocked_coverage_claims_completion")

    privacy = payload.get("privacy") if isinstance(payload.get("privacy"), dict) else {}
    for key in ("rawCredentialExposed", "rawSessionTokenExposed", "envValuesExposed"):
        if privacy.get(key) is not False:
            issues.append(f"privacy_flag_not_false:{key}")

    return not issues, issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Origin Edition Gold requirement coverage.")
    parser.add_argument(
        "--coverage",
        type=Path,
        default=gold_requirement_coverage_from_env(),
    )
    parser.add_argument("--require-gold", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ok, issues = verify(args.coverage, require_gold=args.require_gold)
    if not ok:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    print("origin edition gold requirement coverage verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
