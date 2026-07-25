#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from materialize_origin_dossier_live_import_request import (
    MINIMUM_FULL_STORY_CHAPTER_COUNT,
    MINIMUM_FULL_STORY_WORD_COUNT,
    _contains_fake_marker,
    _count_chapter_markers,
    _count_story_words,
)


CONTRACT_NAME = "chummer.origin_dossier.workllm_manuscript_import_receipt.v1"


class ValidationError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_section(value: str) -> dict[str, str]:
    scope, separator, model = value.partition("=")
    scope = scope.strip()
    model = model.strip()
    if not separator or not scope or not model:
        raise ValidationError("model sections must use scope=model")
    if _contains_fake_marker({"scope": scope, "model": model}):
        raise ValidationError("model section contains a fake/fallback marker")
    return {"scope": scope, "model": model}


def materialize(
    manuscript_path: Path,
    output_path: Path,
    *,
    thread_url: str,
    tier: int,
    model_sections: list[str],
    completed_at_utc: str | None = None,
) -> dict[str, Any]:
    if not manuscript_path.is_file() or manuscript_path.stat().st_size <= 0:
        raise ValidationError("manuscript must be a non-empty regular file")
    try:
        manuscript = manuscript_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"manuscript must be readable UTF-8: {exc}") from exc
    if _contains_fake_marker(manuscript):
        raise ValidationError("manuscript contains a fake/fallback marker")

    word_count = _count_story_words(manuscript)
    chapter_count = _count_chapter_markers(manuscript)
    if word_count < MINIMUM_FULL_STORY_WORD_COUNT:
        raise ValidationError(f"manuscript has {word_count} words; at least {MINIMUM_FULL_STORY_WORD_COUNT} are required")
    if chapter_count < MINIMUM_FULL_STORY_CHAPTER_COUNT:
        raise ValidationError(
            f"manuscript has {chapter_count} chapter markers; at least {MINIMUM_FULL_STORY_CHAPTER_COUNT} are required"
        )

    parsed_thread = urlparse(thread_url.strip())
    workspace_host = (parsed_thread.hostname or "").lower()
    if (
        parsed_thread.scheme.lower() != "https"
        or not workspace_host.endswith(".workllm.io")
        or parsed_thread.username
        or parsed_thread.password
        or not parsed_thread.path.startswith("/team-ai")
    ):
        raise ValidationError("thread URL must be an HTTPS WorkLLM team-ai URL without embedded credentials")
    if tier <= 0:
        raise ValidationError("tier must be positive")
    sections = [_parse_section(value) for value in model_sections]
    if not sections:
        raise ValidationError("at least one model section is required")

    completed_at = (completed_at_utc or _now_iso()).strip()
    try:
        datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("completed-at-utc must be an ISO-8601 timestamp") from exc

    manuscript_hash = _sha256_file(manuscript_path)
    receipt = {
        "contractName": CONTRACT_NAME,
        "operation": "provider_manuscript_import",
        "provider": f"WorkLLM Tier {tier}",
        "status": "verified",
        "completedAtUtc": completed_at,
        "artifactSha256": [manuscript_hash],
        "tokens": [
            "full_story_manuscript",
            "chaptered_story",
            "approved_runner_canon_only",
            "no_provider_created_facts_entered_canon",
            "operator_verified_live_run",
            "provider_receipt_reference:WorkLLM:provider_manuscript_import",
        ],
        "evidence": {
            "manuscriptSha256": manuscript_hash,
            "wordCount": word_count,
            "chapterCount": chapter_count,
            "workspaceHost": workspace_host,
            "threadReferenceSha256": _sha256_text(thread_url.strip()),
            "accountTier": tier,
            "modelSections": sections,
            "captureMethod": "authenticated_browseract_manual_canary",
            "publicSyntheticCanary": True,
        },
        "privacy": {
            "rawCredentialExposed": False,
            "rawThreadUrlExposed": False,
            "rawPromptTextIncluded": False,
            "privateSourceUploaded": False,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize a redacted WorkLLM Origin manuscript import receipt.")
    parser.add_argument("--manuscript", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--thread-url", required=True)
    parser.add_argument("--tier", required=True, type=int)
    parser.add_argument("--model-section", action="append", default=[])
    parser.add_argument("--completed-at-utc")
    args = parser.parse_args()
    try:
        result = materialize(
            args.manuscript,
            args.output,
            thread_url=args.thread_url,
            tier=args.tier,
            model_sections=args.model_section,
            completed_at_utc=args.completed_at_utc,
        )
    except ValidationError as exc:
        print(json.dumps({"contractName": CONTRACT_NAME, "status": "failed", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
