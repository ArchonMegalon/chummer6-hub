#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from chummer_content_provider_contracts import (
    load_json,
    parse_chapter_specs,
    parse_export_specs,
    require_existing_file,
    sha256_file,
    write_json,
)


def build_receipt(args: argparse.Namespace) -> dict:
    packet_path = require_existing_file(args.packet)
    outline_path = require_existing_file(args.outline)
    packet = load_json(packet_path)
    chapters = parse_chapter_specs(args.chapter)
    exports = parse_export_specs(args.export)
    approved_count = sum(1 for chapter in chapters if chapter["review_status"] == "approved")
    return {
        "contract_name": "chummer.firstbook_premium_receipt.v1",
        "status": "chapter_review_required" if approved_count != len(chapters) else "review_complete",
        "provider": "first_book_ai",
        "packet_id": packet["packet_id"],
        "source_packet_refs": packet.get("source_packet_refs") or [],
        "source_packet_path": str(packet_path),
        "outline_path": str(outline_path),
        "outline_sha256": sha256_file(outline_path),
        "chapters": [
            {
                "chapter": chapter["chapter"],
                "title": chapter["title"],
                "markdown_path": chapter["markdown_path"],
                "markdown_sha256": chapter["markdown_sha256"],
                "review_status": chapter["review_status"],
            }
            for chapter in chapters
        ],
        "exports": exports,
        "validation": {
            "source_binding": "pass",
            "copyright": "pending",
            "private_data": "pending",
            "release_claims": "pending",
            "human_review": "pass" if approved_count == len(chapters) else "partial",
        },
        "publication_allowed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize a First Book premium receipt.")
    parser.add_argument("--packet", required=True)
    parser.add_argument("--outline", required=True)
    parser.add_argument("--chapter", action="append", default=[], help="NUMBER|TITLE|PATH|REVIEW_STATUS")
    parser.add_argument("--export", action="append", default=[], help="FORMAT|PATH")
    parser.add_argument("--out", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    write_json(args.out, build_receipt(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
