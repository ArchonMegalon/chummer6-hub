#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys

from absolute_completion_common import LocalHubApp, RUN_SERVICES_ROOT, completion_path, now_iso, write_json, write_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the retained V4 and added V5 janitor gates and aggregate their results.")
    parser.add_argument("--final", action="store_true", help="Run the final gate set.")
    parser.add_argument("--include-live", default="", help="Optional live base URL for the public scans and route proof.")
    return parser.parse_args()


def build_commands(base_url: str, *, allow_participate_unavailable: bool = False) -> list[list[str]]:
    public_shell_command = ["python3", "scripts/public_shell_minimal_truth_gate.py", "--base-url", base_url]
    if allow_participate_unavailable:
        public_shell_command.append("--allow-participate-unavailable")
    return [
        ["python3", "scripts/check_completion_design_docs.py"],
        ["python3", "scripts/diff_public_manifest_live.py"],
        ["python3", "scripts/reconcile_public_route_families.py"],
        ["python3", "scripts/verify_package_public_routes.py"],
        ["python3", "scripts/participation_notification_e2e.py"],
        ["python3", "scripts/operator_notification_privacy_gate.py"],
        ["python3", "scripts/verify_pwa_notification_runtime.py", "--base-url", base_url],
        ["python3", "scripts/verify_mobile_pwa_public_projection.py", "--base-url", base_url],
        ["python3", "scripts/verify_blazor_execution_horizon_bridge.py"],
        ["python3", "scripts/validate_engagement_drivers_matrix.py"],
        ["python3", "scripts/engagement_backlog_validate.py"],
        ["python3", "scripts/feedback_loop_e2e.py", "--stub-delivery", "--with-impact-receipt"],
        ["python3", "scripts/public_forbidden_string_scan.py", "--base-url", base_url],
        ["python3", "scripts/public_operator_leak_scan.py", "--base-url", base_url],
        ["python3", "scripts/gamification_public_copy_gate.py", "--base-url", base_url],
        ["python3", "scripts/public_copy_readability_gate.py", "--base-url", base_url],
        ["python3", "scripts/public_copy_truth_gate.py", "--base-url", base_url, "--route", "/feedback"],
        public_shell_command,
        ["python3", "scripts/verify_public_routes_from_manifest.py", "--strict-positive", "--seed-receipts", "--base-url", base_url],
    ]


def run_commands(commands: list[list[str]]) -> tuple[list[dict[str, object]], int]:
    results: list[dict[str, object]] = []
    overall_status = 0
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=RUN_SERVICES_ROOT,
            capture_output=True,
            text=True,
        )
        results.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        if completed.returncode != 0:
            overall_status = completed.returncode
    return results, overall_status


def main() -> int:
    args = parse_args()
    base_url = args.include_live.rstrip("/")
    if base_url:
        results, overall_status = run_commands(build_commands(base_url))
    else:
        with LocalHubApp() as app:
            base_url = app.base_url
            results, overall_status = run_commands(build_commands(base_url, allow_participate_unavailable=True))

    payload = {
        "contract_name": "chummer.run_gold_janitor",
        "status": "pass" if overall_status == 0 else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "final": args.final,
        "results": [
            {
                "command": " ".join(result["command"]),
                "returncode": result["returncode"],
            }
            for result in results
        ],
    }
    write_json(completion_path("RUN_GOLD_JANITOR.generated.json"), payload)

    lines = [
        "# Gold janitor final audit",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Status: `{payload['status']}`",
        f"- Base URL: {base_url or 'local-app defaults' }",
        "",
        "## Command results",
        "",
    ]
    for result in results:
        lines.append(f"- `{ ' '.join(result['command']) }` -> `{result['returncode']}`")
    write_text(completion_path("JANITOR_FINAL_AUDIT.md"), "\n".join(lines))
    return overall_status


if __name__ == "__main__":
    raise SystemExit(main())
