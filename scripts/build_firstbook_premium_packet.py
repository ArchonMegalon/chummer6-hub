#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from chummer_content_provider_contracts import parse_bool, validate_firstbook_forbidden_material, write_json


def build_packet(args: argparse.Namespace) -> dict:
    return {
        "contract_name": "chummer.firstbook_premium_packet.v1",
        "packet_id": args.packet_id.strip(),
        "source_packet_refs": [item.strip() for item in args.source_packet_ref if item.strip()],
        "book_title": args.book_title.strip(),
        "audience": args.audience.strip(),
        "style_profile": args.style_profile.strip(),
        "chapter_count": args.chapter_count,
        "approved_claims_only": True,
        "forbidden_material": validate_firstbook_forbidden_material(args.forbidden_material),
        "human_review_required_per_chapter": args.human_review_required_per_chapter,
        "publication_allowed": args.publication_allowed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a First Book premium packet.")
    parser.add_argument("--packet-id", required=True)
    parser.add_argument("--source-packet-ref", action="append", default=[])
    parser.add_argument("--book-title", required=True)
    parser.add_argument("--audience", required=True)
    parser.add_argument("--style-profile", required=True)
    parser.add_argument("--chapter-count", type=int, default=8)
    parser.add_argument("--forbidden-material", action="append", default=[])
    parser.add_argument("--human-review-required-per-chapter", type=parse_bool, default=True)
    parser.add_argument("--publication-allowed", type=parse_bool, default=False)
    parser.add_argument("--out", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    write_json(args.out, build_packet(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
