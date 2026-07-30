#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from chummer_content_provider_contracts import load_json, require_existing_file, sha256_file, write_json
from materialize_firstbook_premium_receipt import build_receipt
from verify_firstbook_premium_receipt import verify_receipt


CONTRACT_NAME = "chummer.firstbook_origin_manuscript_intake.v1"
MINIMUM_FULL_STORY_WORD_COUNT = 10_000
MINIMUM_FULL_STORY_CHAPTER_COUNT = 8
CHAPTER_HEADING = re.compile(
    r"^\s{0,3}(?:#{1,2}\s*)?chapter\s+(\d+)\b(?:\s*[-:–—.]\s*|\s+)?(.*)$",
    flags=re.IGNORECASE | re.MULTILINE,
)


class IntakeError(RuntimeError):
    pass


def _count_words(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value, flags=re.UNICODE))


def _split_chapters(manuscript: str) -> list[dict[str, Any]]:
    matches = list(CHAPTER_HEADING.finditer(manuscript))
    chapters: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(manuscript)
        chapter_number = int(match.group(1))
        title = (match.group(2) or "").strip() or f"Chapter {chapter_number}"
        chapters.append(
            {
                "number": chapter_number,
                "title": title,
                "text": manuscript[start:end].strip() + "\n",
            }
        )
    return chapters


def intake(
    *,
    packet_path: Path,
    outline_path: Path,
    manuscript_path: Path,
    output_dir: Path,
    provider_run_ref: str,
    account_alias: str,
) -> dict[str, Any]:
    packet_path = require_existing_file(str(packet_path))
    outline_path = require_existing_file(str(outline_path))
    manuscript_path = require_existing_file(str(manuscript_path))
    provider_run_ref = provider_run_ref.strip()
    if not provider_run_ref:
        raise IntakeError("provider_run_ref is required and must be a non-secret authenticated First Book run reference")

    packet = load_json(packet_path)
    if packet.get("contract_name") != "chummer.firstbook_premium_packet.v1":
        raise IntakeError("unsupported First Book packet contract")
    manuscript_text = manuscript_path.read_text(encoding="utf-8")
    word_count = _count_words(manuscript_text)
    chapters = _split_chapters(manuscript_text)
    expected_chapter_count = int(packet.get("chapter_count") or 0)
    if word_count < MINIMUM_FULL_STORY_WORD_COUNT:
        raise IntakeError(
            f"First Book manuscript has {word_count} words; at least {MINIMUM_FULL_STORY_WORD_COUNT} are required"
        )
    if len(chapters) < MINIMUM_FULL_STORY_CHAPTER_COUNT:
        raise IntakeError(
            f"First Book manuscript has {len(chapters)} chapters; at least {MINIMUM_FULL_STORY_CHAPTER_COUNT} are required"
        )
    if expected_chapter_count != len(chapters):
        raise IntakeError(
            f"First Book packet expects {expected_chapter_count} chapters but the manuscript contains {len(chapters)}"
        )
    chapter_numbers = [int(chapter["number"]) for chapter in chapters]
    if chapter_numbers != list(range(1, len(chapters) + 1)):
        raise IntakeError("First Book manuscript chapter numbers must be unique and sequential from 1")

    output_dir.mkdir(parents=True, exist_ok=True)
    archived_packet = output_dir / "firstbook-packet.json"
    if packet_path.resolve() != archived_packet.resolve():
        shutil.copyfile(packet_path, archived_packet)
    archived_manuscript = output_dir / "firstbook-manuscript.md"
    if manuscript_path.resolve() != archived_manuscript.resolve():
        shutil.copyfile(manuscript_path, archived_manuscript)
    archived_outline = output_dir / "firstbook-outline.md"
    if outline_path.resolve() != archived_outline.resolve():
        shutil.copyfile(outline_path, archived_outline)
    if sha256_file(archived_manuscript) != sha256_file(manuscript_path):
        raise IntakeError("archived First Book manuscript hash does not match the provider export")

    chapter_specs: list[str] = []
    chapter_paths: list[Path] = []
    for chapter in chapters:
        number = int(chapter["number"])
        chapter_path = output_dir / "chapters" / f"chapter-{number:02d}.md"
        chapter_path.parent.mkdir(parents=True, exist_ok=True)
        chapter_path.write_text(str(chapter["text"]), encoding="utf-8")
        chapter_paths.append(chapter_path)
        chapter_specs.append(f"{number}|{chapter['title']}|{chapter_path}|approved")

    draft_receipt = build_receipt(
        SimpleNamespace(
            packet=str(archived_packet),
            outline=str(archived_outline),
            chapter=chapter_specs,
            export=[f"markdown|{archived_manuscript}"],
            manuscript=str(archived_manuscript),
            provider_run_ref=provider_run_ref,
            account_alias=account_alias.strip(),
        )
    )
    draft_receipt_path = output_dir / "firstbook-manuscript.receipt.draft.json"
    draft_receipt_path.write_text(json.dumps(draft_receipt, indent=2) + "\n", encoding="utf-8")
    verified_receipt, passed = verify_receipt(
        SimpleNamespace(receipt=str(draft_receipt_path))
    )
    if not passed or verified_receipt.get("full_manuscript_ready") is not True:
        raise IntakeError("First Book manuscript receipt did not pass authenticated source binding")
    receipt_path = output_dir / "firstbook-manuscript.receipt.json"
    write_json(receipt_path, verified_receipt)
    draft_receipt_path.unlink()

    result = {
        "contractName": CONTRACT_NAME,
        "status": "pass",
        "provider": "First Book AI",
        "operation": "provider_manuscript_intake",
        "fullManuscriptReady": True,
        "manuscriptPath": str(archived_manuscript),
        "manuscriptSha256": sha256_file(archived_manuscript),
        "manuscriptWordCount": word_count,
        "chapterCount": len(chapter_paths),
        "chapterSha256": [sha256_file(path) for path in chapter_paths],
        "receiptPath": str(receipt_path),
        "receiptSha256": sha256_file(receipt_path),
        "rawProviderRunRefIncluded": False,
    }
    intake_receipt_path = output_dir / "firstbook-intake.receipt.json"
    write_json(intake_receipt_path, result)
    return {**result, "intakeReceiptPath": str(intake_receipt_path)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Intake an authenticated First Book Origin Dossier manuscript.")
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--outline", required=True, type=Path)
    parser.add_argument("--manuscript", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--provider-run-ref", required=True)
    parser.add_argument("--account-alias", default="")
    parser.add_argument("--out", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = intake(
        packet_path=args.packet,
        outline_path=args.outline,
        manuscript_path=args.manuscript,
        output_dir=args.output_dir,
        provider_run_ref=args.provider_run_ref,
        account_alias=args.account_alias,
    )
    write_json(args.out, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
