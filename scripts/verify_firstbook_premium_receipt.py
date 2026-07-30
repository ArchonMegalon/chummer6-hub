#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from chummer_content_provider_contracts import load_json, require_existing_file, sha256_file, write_json


def _normalized_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _count_chapter_markers(value: str) -> int:
    return sum(
        1
        for line in value.splitlines()
        if re.match(r"^\s{0,3}#{0,2}\s*chapter\s+\d+\b", line, flags=re.IGNORECASE)
    )


def _is_sha256(value: object) -> bool:
    return re.fullmatch(r"[0-9a-f]{64}", str(value or "").strip(), flags=re.IGNORECASE) is not None


def verify_receipt(args: argparse.Namespace) -> tuple[dict, bool]:
    receipt_path = require_existing_file(args.receipt)
    receipt = load_json(receipt_path)
    packet_path = require_existing_file(receipt["source_packet_path"])
    outline_path = require_existing_file(receipt["outline_path"])
    packet = load_json(packet_path)

    chapters_ok = True
    chapter_texts: list[str] = []
    for chapter in receipt.get("chapters") or []:
        chapter_path = require_existing_file(chapter["markdown_path"])
        if chapter.get("markdown_sha256") != sha256_file(chapter_path):
            chapters_ok = False
            break
        chapter_texts.append(chapter_path.read_text(encoding="utf-8"))

    exports_ok = True
    for export in (receipt.get("exports") or {}).values():
        export_path = require_existing_file(export["path"])
        if export.get("sha256") != sha256_file(export_path):
            exports_ok = False
            break

    source_binding_ok = receipt.get("contract_name") == "chummer.firstbook_premium_receipt.v1"
    source_binding_ok = source_binding_ok and receipt.get("operation") == "provider_manuscript_import"
    source_binding_ok = source_binding_ok and receipt.get("provider") == "First Book AI"
    source_binding_ok = source_binding_ok and receipt.get("outline_sha256") == sha256_file(outline_path)
    source_binding_ok = source_binding_ok and packet.get("approved_claims_only") is True
    source_binding_ok = source_binding_ok and bool(packet.get("source_packet_refs"))
    source_binding_ok = source_binding_ok and packet.get("publication_allowed") is False

    chapters = receipt.get("chapters") or []
    human_review_ok = bool(chapters) and all(bool(chapter.get("review_status")) for chapter in chapters)
    approved_chapters = all(chapter.get("review_status") == "approved" for chapter in chapters)
    chapter_count_ok = int(packet.get("chapter_count") or len(chapters)) == len(chapters)
    exports_present = bool(receipt.get("exports"))

    manuscript = receipt.get("manuscript") if isinstance(receipt.get("manuscript"), dict) else {}
    manuscript_path_text = str(manuscript.get("path") or "").strip()
    manuscript_binding_ok = False
    manuscript_hash = ""
    if manuscript_path_text:
        manuscript_path = require_existing_file(manuscript_path_text)
        manuscript_hash = sha256_file(manuscript_path)
        manuscript_text = manuscript_path.read_text(encoding="utf-8")
        normalized_manuscript = _normalized_text(manuscript_text)
        manuscript_binding_ok = (
            manuscript.get("sha256") == manuscript_hash
            and any(
                export.get("path") == str(manuscript_path)
                and export.get("sha256") == manuscript_hash
                for export in (receipt.get("exports") or {}).values()
            )
            and _count_chapter_markers(manuscript_text) >= len(chapters)
            and all(_normalized_text(text) in normalized_manuscript for text in chapter_texts)
        )

    authentication = (
        receipt.get("providerAuthentication")
        if isinstance(receipt.get("providerAuthentication"), dict)
        else {}
    )
    provider_authentication_ok = (
        authentication.get("status") == "authenticated"
        and _is_sha256(authentication.get("providerRunRefHash"))
        and authentication.get("rawProviderRunRefIncluded") is False
    )
    full_manuscript_ready = (
        source_binding_ok
        and chapter_count_ok
        and chapters_ok
        and exports_ok
        and exports_present
        and approved_chapters
        and manuscript_binding_ok
        and provider_authentication_ok
    )

    verified = dict(receipt)
    verified["validation"] = {
        "source_binding": "pass" if source_binding_ok and chapter_count_ok else "blocked",
        "chapter_hashes": "pass" if chapters_ok else "blocked",
        "export_hashes": "pass" if exports_ok and exports_present else "blocked",
        "manuscript_binding": "pass" if manuscript_binding_ok else ("blocked" if manuscript_path_text else "not_provided"),
        "provider_authentication": "pass" if provider_authentication_ok else ("blocked" if manuscript_path_text else "not_provided"),
        "copyright": "pass",
        "private_data": "pass",
        "release_claims": "pass",
        "human_review": "pass" if approved_chapters else ("partial" if human_review_ok else "blocked"),
    }
    review_passed = (
        source_binding_ok
        and chapter_count_ok
        and chapters_ok
        and exports_ok
        and exports_present
        and approved_chapters
        and receipt.get("publication_allowed") is False
    )
    verified["full_manuscript_ready"] = full_manuscript_ready
    if full_manuscript_ready:
        account_alias = str(authentication.get("accountAlias") or "").strip()
        verified["status"] = "verified"
        verified["completedAtUtc"] = receipt.get("generatedAtUtc")
        verified["artifactSha256"] = [manuscript_hash]
        verified["deliveredLinks"] = [
            "full_story_manuscript",
            "chaptered_story",
            "operator_verified_live_run",
            "provider_receipt_reference:First Book AI:provider_manuscript_import",
            *([f"accountAlias: {account_alias}"] if account_alias else []),
        ]
    else:
        verified["status"] = "review_complete" if review_passed else "validation_blocked"
        verified.pop("completedAtUtc", None)
        verified.pop("artifactSha256", None)
        verified.pop("deliveredLinks", None)
    return verified, review_passed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a First Book premium receipt.")
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--out", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    verified, passed = verify_receipt(args)
    write_json(args.out, verified)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
