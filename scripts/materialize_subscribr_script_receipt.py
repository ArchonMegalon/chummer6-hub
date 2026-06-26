#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from chummer_content_provider_contracts import load_json, require_existing_file, sha256_file, write_json


def build_receipt(args: argparse.Namespace) -> dict:
    packet_path = require_existing_file(args.packet)
    export_path = require_existing_file(args.markdown_export)
    packet = load_json(packet_path)
    mode = str(packet.get("mode") or "").strip()
    origin_mode = mode.startswith("ORIGIN_DOSSIER")
    return {
        "contract_name": "chummer.subscribr_script_receipt.v1",
        "status": "review_required",
        "provider": "subscribr",
        "mode": mode,
        "packet_id": packet["packet_id"],
        "source_packet_path": str(packet_path),
        "script_markdown_path": str(export_path),
        "channel_key": packet.get("subscribr_channel_key"),
        "provider_channel_id": args.provider_channel_id,
        "provider_idea_id": args.provider_idea_id,
        "provider_script_id": args.provider_script_id,
        "source_packet_sha256": sha256_file(packet_path),
        "script_markdown_sha256": sha256_file(export_path),
        "source_heads": packet.get("source_heads") or {},
        "validation": {
            "source_binding": "pass",
            "private_data": "pending",
            "copyright": "pending",
            "mechanics_unchanged": "pending",
            "release_claims": "pending",
            "origin_canon": "pending" if origin_mode else "not_applicable",
            "approval": "pending",
        },
        "publication_allowed": False,
        "media_factory_allowed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize a Subscribr script receipt.")
    parser.add_argument("--packet", required=True)
    parser.add_argument("--markdown-export", required=True)
    parser.add_argument("--provider-channel-id", required=True)
    parser.add_argument("--provider-idea-id", required=True)
    parser.add_argument("--provider-script-id", required=True)
    parser.add_argument("--out", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    write_json(args.out, build_receipt(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
