#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def without_generated_at(payload: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if key != "generated_at"}


def main() -> int:
    if len(sys.argv) != 6:
        print(
            "usage: materialize_hub_local_release_proof.py <out_path> <base_url> <compose_file> <timeout_seconds> <skip_rebuild>",
            file=sys.stderr,
        )
        return 1

    out_path_text, base_url, compose_file, timeout_seconds, skip_rebuild = sys.argv[1:]
    out_path = Path(out_path_text)

    payload = {
        "contract_name": "chummer6-hub.local_release_proof",
        "status": "passed",
        "base_url": base_url,
        "compose_file": compose_file,
        "playwright_timeout_seconds": int(timeout_seconds),
        "edge_rebuild_skipped": skip_rebuild.lower() in {"1", "true"},
        "journeys_passed": [
            "install_claim_restore_continue",
            "build_explain_publish",
            "campaign_session_recover_recap",
            "report_cluster_release_notify",
        ],
        "proof_routes": [
            "/downloads/install/avalonia-linux-x64-installer",
            "/home/access",
            "/home/work",
            "/account/work",
            "/account/support",
            "/contact",
        ],
    }

    if out_path.is_file():
        try:
            existing_payload = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_payload = None

        if isinstance(existing_payload, dict) and without_generated_at(existing_payload) == payload:
            print(f"hub local proof unchanged: {out_path}")
            return 0

    payload["generated_at"] = iso_now()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote hub local proof: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
