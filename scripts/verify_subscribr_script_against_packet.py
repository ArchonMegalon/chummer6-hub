#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from chummer_content_provider_contracts import (
    detect_forbidden_claims,
    detect_missing_required_claims,
    load_json,
    packet_private_data_is_safe,
    require_existing_file,
    sha256_file,
    write_json,
)


def verify_receipt(args: argparse.Namespace) -> tuple[dict, bool]:
    receipt_path = require_existing_file(args.receipt)
    receipt = load_json(receipt_path)
    packet_path = require_existing_file(receipt["source_packet_path"])
    script_path = require_existing_file(receipt["script_markdown_path"])
    packet = load_json(packet_path)
    script_text = script_path.read_text(encoding="utf-8")
    missing_claims = detect_missing_required_claims(script_text, list(packet.get("allowed_claims") or []))
    forbidden_claims = detect_forbidden_claims(script_text, list(packet.get("forbidden_claims") or []))
    packet_hash_ok = receipt.get("source_packet_sha256") == sha256_file(packet_path)
    script_hash_ok = receipt.get("script_markdown_sha256") == sha256_file(script_path)
    private_data_safe = packet_private_data_is_safe(packet)
    sourcebook_safe = not bool((packet.get("private_data") or {}).get("contains_sourcebook_prose"))
    origin_mode = str(packet.get("mode") or "").startswith("ORIGIN_DOSSIER")

    validation = {
        "source_binding": "pass" if packet_hash_ok and script_hash_ok else "blocked",
        "required_claims": "pass" if not missing_claims else "blocked",
        "forbidden_claims": "pass" if not forbidden_claims else "blocked",
        "private_data": "pass" if private_data_safe else "blocked",
        "copyright": "pass" if sourcebook_safe else "blocked",
        "mechanics_unchanged": "pass" if not forbidden_claims else "blocked",
        "release_claims": "pass" if not forbidden_claims else "blocked",
        "origin_canon": "pass" if origin_mode and not forbidden_claims else ("not_applicable" if not origin_mode else "blocked"),
        "approval": "pending",
    }
    verified = dict(receipt)
    verified["validation"] = validation
    if missing_claims:
        verified["missing_required_claims"] = missing_claims
    if forbidden_claims:
        verified["detected_forbidden_claims"] = forbidden_claims
    passed = (
        packet_hash_ok
        and script_hash_ok
        and not missing_claims
        and not forbidden_claims
        and private_data_safe
        and sourcebook_safe
    )
    verified["status"] = "review_required" if passed else "validation_blocked"
    return verified, passed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a Subscribr script export against its packet.")
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
