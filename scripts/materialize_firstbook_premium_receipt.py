#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from chummer_content_provider_contracts import (
    load_json,
    parse_chapter_specs,
    parse_export_specs,
    require_existing_file,
    sha256_file,
    sha256_text,
    write_json,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_receipt(args: argparse.Namespace) -> dict:
    packet_path = require_existing_file(args.packet)
    outline_path = require_existing_file(args.outline)
    packet = load_json(packet_path)
    chapters = parse_chapter_specs(args.chapter)
    exports = parse_export_specs(args.export)
    approved_count = sum(1 for chapter in chapters if chapter["review_status"] == "approved")
    expected_chapter_count = int(packet.get("chapter_count") or 0)
    chapter_set_complete = expected_chapter_count > 0 and len(chapters) == expected_chapter_count
    review_complete = chapter_set_complete and approved_count == len(chapters)
    manuscript_path_text = str(getattr(args, "manuscript", "") or "").strip()
    provider_run_ref = str(getattr(args, "provider_run_ref", "") or "").strip()
    account_alias = str(getattr(args, "account_alias", "") or "").strip()
    manuscript = require_existing_file(manuscript_path_text) if manuscript_path_text else None
    if manuscript is not None and not provider_run_ref:
        raise ValueError("--provider-run-ref is required when materializing a full First Book manuscript")

    receipt = {
        "contract_name": "chummer.firstbook_premium_receipt.v1",
        "operation": "provider_manuscript_import",
        "status": "review_complete" if review_complete else "chapter_review_required",
        "provider": "First Book AI",
        "generatedAtUtc": _now_iso(),
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
        "manuscript": (
            {
                "path": str(manuscript),
                "sha256": sha256_file(manuscript),
            }
            if manuscript is not None
            else None
        ),
        "providerAuthentication": {
            "status": "authenticated" if provider_run_ref else "not_provided",
            "accountAlias": account_alias,
            "providerRunRefHash": sha256_text(provider_run_ref) if provider_run_ref else "",
            "rawProviderRunRefIncluded": False,
        },
        "validation": {
            "source_binding": "pass" if chapter_set_complete else "blocked",
            "chapter_hashes": "pending",
            "export_hashes": "pending",
            "manuscript_binding": "pending" if manuscript is not None else "not_provided",
            "provider_authentication": "pending" if provider_run_ref else "not_provided",
            "copyright": "pending",
            "private_data": "pending",
            "release_claims": "pending",
            "human_review": "pass" if review_complete else ("partial" if approved_count else "blocked"),
        },
        "full_manuscript_ready": False,
        "publication_allowed": False,
    }
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize a First Book premium receipt.")
    parser.add_argument("--packet", required=True)
    parser.add_argument("--outline", required=True)
    parser.add_argument("--chapter", action="append", default=[], help="NUMBER|TITLE|PATH|REVIEW_STATUS")
    parser.add_argument("--export", action="append", default=[], help="FORMAT|PATH")
    parser.add_argument("--manuscript", default="", help="Complete UTF-8 First Book manuscript used by Origin Dossier.")
    parser.add_argument("--provider-run-ref", default="", help="Non-secret authenticated First Book run reference; stored only as SHA-256.")
    parser.add_argument("--account-alias", default="", help="Configured non-secret First Book account alias.")
    parser.add_argument("--out", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    write_json(args.out, build_receipt(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
