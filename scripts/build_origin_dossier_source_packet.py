#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from chummer_content_provider_contracts import (
    approval_block,
    normalize_claims,
    parse_bool,
    parse_iso_utc,
    parse_mapping,
    parse_sources,
    private_data_block,
    require_existing_file,
    sha256_file,
    write_json,
)


def build_packet(args: argparse.Namespace) -> dict:
    origin_canon_path = require_existing_file(args.origin_canon_path)
    mechanics_snapshot_path = require_existing_file(args.mechanics_snapshot_path)
    packet = {
        "contract_name": "chummer.content_source_packet.v1",
        "packet_id": args.packet_id.strip(),
        "mode": args.mode.strip(),
        "target_provider": args.target_provider.strip(),
        "title": args.title.strip(),
        "audience": args.audience.strip(),
        "language": args.language.strip(),
        "target_output": args.target_output.strip(),
        "source_heads": parse_mapping(args.source_head),
        "sources": parse_sources(args.source),
        "allowed_claims": normalize_claims(args.allowed_claim),
        "forbidden_claims": normalize_claims(args.forbidden_claim),
        "private_data": private_data_block(
            contains_private_runner=args.contains_private_runner,
            contains_gm_secret=args.contains_gm_secret,
            contains_sourcebook_prose=args.contains_sourcebook_prose,
        ),
        "approval": approval_block(
            human_review_required=args.human_review_required,
            gm_approval_required=args.gm_approval_required,
            player_approval_required=args.player_approval_required,
            publication_allowed=args.publication_allowed,
        ),
        "origin_dossier": {
            "runner_ref": args.runner_ref.strip(),
            "campaign_ref": args.campaign_ref.strip(),
            "origin_canon_sha256": sha256_file(origin_canon_path),
            "mechanics_snapshot_sha256": sha256_file(mechanics_snapshot_path),
            "public_projection": args.public_projection.strip(),
            "gm_secret_included": args.gm_secret_included,
        },
        "expires_at": parse_iso_utc(args.expires_at),
    }
    if args.target_words is not None:
        packet["target_words"] = args.target_words
    if args.subscribr_channel_key:
        packet["subscribr_channel_key"] = args.subscribr_channel_key.strip()
    return packet


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an Origin Dossier source packet.")
    parser.add_argument("--packet-id", required=True)
    parser.add_argument("--mode", default="ORIGIN_DOSSIER_NARRATIVE")
    parser.add_argument("--target-provider", default="subscribr")
    parser.add_argument("--subscribr-channel-key", default="runner-origin-dossiers")
    parser.add_argument("--title", required=True)
    parser.add_argument("--audience", required=True)
    parser.add_argument("--language", default="en-US")
    parser.add_argument("--target-output", default="narration_script")
    parser.add_argument("--target-words", type=int)
    parser.add_argument("--runner-ref", required=True)
    parser.add_argument("--campaign-ref", required=True)
    parser.add_argument("--origin-canon-path", required=True)
    parser.add_argument("--mechanics-snapshot-path", required=True)
    parser.add_argument("--public-projection", default="player_safe")
    parser.add_argument("--gm-secret-included", type=parse_bool, default=False)
    parser.add_argument("--source-head", action="append", default=[], help="KEY=VALUE")
    parser.add_argument("--source", action="append", default=[], help="PATH|AUTHORITY|CLASSIFICATION")
    parser.add_argument("--allowed-claim", action="append", default=[])
    parser.add_argument("--forbidden-claim", action="append", default=[])
    parser.add_argument("--contains-private-runner", type=parse_bool, default=False)
    parser.add_argument("--contains-gm-secret", type=parse_bool, default=False)
    parser.add_argument("--contains-sourcebook-prose", type=parse_bool, default=False)
    parser.add_argument("--human-review-required", type=parse_bool, default=True)
    parser.add_argument("--gm-approval-required", type=parse_bool, default=True)
    parser.add_argument("--player-approval-required", type=parse_bool, default=True)
    parser.add_argument("--publication-allowed", type=parse_bool, default=False)
    parser.add_argument("--expires-at", required=True)
    parser.add_argument("--out", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    write_json(args.out, build_packet(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
