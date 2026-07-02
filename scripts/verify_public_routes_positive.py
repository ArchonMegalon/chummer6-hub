#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from absolute_completion_common import LocalHubApp, RUN_SERVICES_ROOT, completion_path, now_iso, write_json, write_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate positive public route proof from the manifest verifier.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def run_source_verifier(base_url: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="chummer-public-route-proof-") as temp_dir:
        output_path = Path(temp_dir) / "source-route-proof.json"
        command = [
            sys.executable,
            "scripts/verify_public_routes_from_manifest.py",
            "--base-url",
            base_url,
            "--output",
            str(output_path),
        ]
        result = subprocess.run(command, cwd=RUN_SERVICES_ROOT, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "route verifier failed")
        if output_path.is_file():
            return json.loads(output_path.read_text(encoding="utf-8"))
        if result.stdout.strip():
            return json.loads(result.stdout)
        raise RuntimeError("route verifier did not emit JSON proof")


def build_output(source_payload: dict, base_url: str) -> dict:
    public_routes = [route for route in source_payload.get("routes", []) if route.get("mode") == "public_route"]
    registered_fallbacks = [route for route in source_payload.get("routes", []) if route.get("mode") == "registered_fallback"]
    failures = [route for route in public_routes + registered_fallbacks if not route.get("success")]

    payload = {
        "contract_name": "chummer.public_route_positive_proof",
        "status": "pass" if not failures and public_routes else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "summary": {
            "public_route_count": len(public_routes),
            "registered_fallback_count": len(registered_fallbacks),
            "failed_count": len(failures),
        },
        "public_routes": public_routes,
        "registered_fallbacks": registered_fallbacks,
        "failures": failures,
    }
    return payload


def write_strictness_report(source_payload: dict, positive_payload: dict) -> None:
    auth_routes = [route for route in source_payload.get("routes", []) if route.get("mode") == "auth_operation"]
    controller_contracts = [route for route in source_payload.get("routes", []) if route.get("mode") == "controller_contract"]
    lines = [
        "# Route proof strictness report",
        "",
        f"- Generated: {now_iso()}",
        f"- Positive public routes: {positive_payload['summary']['public_route_count']}",
        f"- Registered anonymous fallback checks: {positive_payload['summary']['registered_fallback_count']}",
        f"- Negative auth-operation checks kept separate: {len(auth_routes)}",
        f"- Receipt/controller-contract routes kept separate: {len(controller_contracts)}",
        "",
        "## Strictness rule",
        "",
        "`400`, `404`, and `405` are not counted as positive product-route success.",
        "Only explicit auth-operation negatives keep `400` or `405` as acceptable evidence, and receipt routes are proven separately through created objects with `200` receipt pages.",
        "",
        "## Result",
        "",
        f"- Status: `{positive_payload['status']}`",
        f"- Failed public or registered-fallback routes: {positive_payload['summary']['failed_count']}",
    ]
    write_text(completion_path("ROUTE_PROOF_STRICTNESS_REPORT.md"), "\n".join(lines))


def main() -> int:
    args = parse_args()
    if args.base_url:
        source_payload = run_source_verifier(args.base_url)
        positive_payload = build_output(source_payload, args.base_url)
        write_json(completion_path("PUBLIC_ROUTE_POSITIVE_PROOF.generated.json"), positive_payload)
        write_strictness_report(source_payload, positive_payload)
        return 0 if positive_payload["status"] == "pass" else 1

    with LocalHubApp() as app:
        source_payload = run_source_verifier(app.base_url)
        positive_payload = build_output(source_payload, app.base_url)
        write_json(completion_path("PUBLIC_ROUTE_POSITIVE_PROOF.generated.json"), positive_payload)
        write_strictness_report(source_payload, positive_payload)
        return 0 if positive_payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
