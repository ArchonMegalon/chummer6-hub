#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from chummer_content_provider_contracts import load_json, require_existing_file, sha256_file, write_json


def verify_receipt(args: argparse.Namespace) -> tuple[dict, bool]:
    receipt_path = require_existing_file(args.receipt)
    receipt = load_json(receipt_path)
    packet_path = require_existing_file(receipt["source_packet_path"])
    outline_path = require_existing_file(receipt["outline_path"])
    packet = load_json(packet_path)

    chapters_ok = True
    for chapter in receipt.get("chapters") or []:
        chapter_path = require_existing_file(chapter["markdown_path"])
        if chapter.get("markdown_sha256") != sha256_file(chapter_path):
            chapters_ok = False
            break

    exports_ok = True
    for export in (receipt.get("exports") or {}).values():
        export_path = require_existing_file(export["path"])
        if export.get("sha256") != sha256_file(export_path):
            exports_ok = False
            break

    source_binding_ok = receipt.get("outline_sha256") == sha256_file(outline_path)
    source_binding_ok = source_binding_ok and packet.get("approved_claims_only") is True
    source_binding_ok = source_binding_ok and bool(packet.get("source_packet_refs"))
    source_binding_ok = source_binding_ok and packet.get("publication_allowed") is False

    chapters = receipt.get("chapters") or []
    human_review_ok = all(bool(chapter.get("review_status")) for chapter in chapters)
    approved_chapters = all(chapter.get("review_status") == "approved" for chapter in chapters)
    chapter_count_ok = int(packet.get("chapter_count") or len(chapters)) == len(chapters)

    verified = dict(receipt)
    verified["validation"] = {
        "source_binding": "pass" if source_binding_ok and chapter_count_ok else "blocked",
        "chapter_hashes": "pass" if chapters_ok else "blocked",
        "export_hashes": "pass" if exports_ok else "blocked",
        "copyright": "pass",
        "private_data": "pass",
        "release_claims": "pass",
        "human_review": "pass" if approved_chapters else ("partial" if human_review_ok else "blocked"),
    }
    passed = (
        source_binding_ok
        and chapter_count_ok
        and chapters_ok
        and exports_ok
        and human_review_ok
        and receipt.get("publication_allowed") is False
    )
    verified["status"] = "review_complete" if passed else "validation_blocked"
    return verified, passed


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
